"""Training: lesson pages, quiz scoring, linking attempts back to a person, video."""
from types import SimpleNamespace

from sqlmodel import select

from app.models import QuizResult, Target, TrainingModule, TrainingQuestion
from app.services.video import video_info


def _module_and_questions(session_factory):
    with session_factory() as s:
        module = s.exec(select(TrainingModule).order_by(TrainingModule.order)).first()
        qs = s.exec(select(TrainingQuestion).where(TrainingQuestion.module_id == module.id)
                    .order_by(TrainingQuestion.order)).all()
    return module, qs


def test_lesson_page_renders(client, session_factory):
    module, qs = _module_and_questions(session_factory)
    r = client.get(f"/training/{module.slug}")
    assert r.status_code == 200
    assert module.title in r.text
    assert qs[0].prompt.split("'")[0] in r.text  # Jinja escapes apostrophes


def test_unknown_module_404(client):
    assert client.get("/training/nope").status_code == 404
    assert client.post("/training/nope/quiz", data={}).status_code == 404


def test_quiz_scores_only_correct_answers(client, session_factory):
    module, qs = _module_and_questions(session_factory)
    answers = {f"q{q.id}": str(q.correct_index) for q in qs}
    answers[f"q{qs[0].id}"] = str((qs[0].correct_index + 1) % 4)   # one wrong
    answers[f"q{qs[1].id}"] = "not-a-number"                        # garbage ignored
    r = client.post(f"/training/{module.slug}/quiz", data=answers)
    assert r.status_code == 200
    with session_factory() as s:
        result = s.exec(select(QuizResult)).one()
    assert (result.score, result.total) == (len(qs) - 2, len(qs))
    assert result.user_id is None


def test_quiz_links_attempt_to_person_via_token(client, session_factory):
    client.post("/users", data={"email": "q@example.com", "consented": "on"})
    client.post("/campaigns", data={"name": "C", "subject": "S",
                                    "from_name": "IT", "from_email": "it@example.com"})
    from app.models import Campaign, User
    with session_factory() as s:
        uid = s.exec(select(User.id)).first()
        cid = s.exec(select(Campaign.id)).first()
    client.post(f"/campaigns/{cid}/targets", data={"user_ids": uid})
    with session_factory() as s:
        token = s.exec(select(Target.token)).first()

    module, qs = _module_and_questions(session_factory)
    data = {f"q{q.id}": str(q.correct_index) for q in qs}
    client.post(f"/t/training/{token}/{module.slug}/quiz", data=data)
    with session_factory() as s:
        result = s.exec(select(QuizResult)).one()
    assert result.user_id == uid and result.score == len(qs)


def _mod(url="", poster=""):
    return SimpleNamespace(video_url=url, video_poster=poster)


def test_video_info_none_without_url():
    assert video_info(_mod()) is None
    assert video_info(_mod("   ")) is None


def test_video_info_youtube_variants():
    for url in ("https://www.youtube.com/watch?v=abc123&t=5",
                "https://youtu.be/abc123",
                "https://www.youtube.com/embed/abc123/"):
        info = video_info(_mod(url))
        assert info["kind"] == "youtube"
        assert info["embed"] == "https://www.youtube.com/embed/abc123"


def test_video_info_vimeo():
    info = video_info(_mod("https://vimeo.com/76979871/"))
    assert info == {"kind": "vimeo", "embed": "https://player.vimeo.com/video/76979871",
                    "ready": True, "url": "https://vimeo.com/76979871/"}


def test_video_info_local_file_readiness():
    missing = video_info(_mod("/static/videos/definitely-missing.mp4", " /static/p.png "))
    assert missing["kind"] == "file" and missing["ready"] is False
    assert missing["poster"] == "/static/p.png"
    external = video_info(_mod("https://cdn.example.com/clip.mp4"))
    assert external["kind"] == "file" and external["ready"] is True


def test_seeded_modules_have_official_sources(client, session_factory):
    with session_factory() as s:
        modules = s.exec(select(TrainingModule)).all()
    for m in modules:
        assert m.sources, f"{m.slug} has no sources"
        assert all(src["url"].startswith("https://") for src in m.sources)
        assert "youtube.com" in m.video_url or any(src["kind"] == "video" for src in m.sources)
    module = modules[0]
    r = client.get(f"/training/{module.slug}")
    assert "Watch &amp; read more" in r.text
    assert module.sources[0]["url"] in r.text
    assert 'rel="noopener noreferrer"' in r.text


def test_sources_property_drops_bad_entries():
    m = TrainingModule(slug="x", title="x", sources_json='[{"url": "javascript:alert(1)"},'
                       '{"url": "https://cisa.gov", "title": "ok"}, "junk"]')
    assert [s["url"] for s in m.sources] == ["https://cisa.gov"]
    assert TrainingModule(slug="y", title="y", sources_json="not json").sources == []
    assert TrainingModule(slug="z", title="z", sources_json='[{"url": 5}]').sources == []
    assert TrainingModule(slug="w", title="w", sources_json='{"url": "https://x"}').sources == []


def test_backfill_fills_empty_sources_only(session_factory):
    from app.database import _backfill_sources
    with session_factory() as s:
        a, b = s.exec(select(TrainingModule).order_by(TrainingModule.order)).all()[:2]
        a.sources_json = "[]"
        b.sources_json = '[{"url": "https://example.com", "title": "custom"}]'
        s.add(a)
        s.add(b)
        s.commit()
        _backfill_sources(s)
        s.refresh(a)
        s.refresh(b)
    assert a.sources and a.sources[0]["publisher"] == "CISA"
    assert b.sources[0]["title"] == "custom"


def test_retired_modules_are_removed(session_factory):
    from app.database import _RETIRED_SLUGS, _seed_training
    with session_factory() as s:
        old = TrainingModule(slug=_RETIRED_SLUGS[0], title="Old")
        s.add(old)
        s.commit()
        s.add(TrainingQuestion(module_id=old.id, prompt="?", choices_json="[]", correct_index=0))
        s.add(QuizResult(module_id=old.id, score=1, total=1))
        s.commit()
        old_id = old.id
    _seed_training()
    with session_factory() as s:
        slugs = set(s.exec(select(TrainingModule.slug)).all())
        assert not slugs & set(_RETIRED_SLUGS)
        assert len(slugs) == 5
        assert not s.exec(select(QuizResult).where(QuizResult.module_id == old_id)).all()
        assert not s.exec(select(TrainingQuestion).where(TrainingQuestion.module_id == old_id)).all()


def _drill_token(client, session_factory) -> tuple[int, str]:
    from app.models import Campaign, User
    client.post("/users", data={"email": "staff@example.com", "name": "Staff", "consented": "on"})
    client.post("/campaigns", data={"name": "C", "subject": "S",
                                    "from_name": "IT", "from_email": "it@example.com"})
    with session_factory() as s:
        uid = s.exec(select(User.id)).first()
        cid = s.exec(select(Campaign.id)).first()
    client.post(f"/campaigns/{cid}/targets", data={"user_ids": uid})
    with session_factory() as s:
        return uid, s.exec(select(Target.token)).first()


def test_landing_training_link_works_for_staff_without_login(client, anon, session_factory):
    """Regression: the landing page's training link used to point at the
    admin-only /training path, so staff were bounced to the admin login."""
    _, token = _drill_token(client, session_factory)
    landing = anon.get(f"/t/click/{token}")
    assert landing.status_code == 200
    href = landing.text.split('class="cta" href="')[1].split('"')[0]
    assert href.startswith(f"/t/training/{token}/")
    r = anon.get(href, follow_redirects=False)
    assert r.status_code == 200
    assert "Quick quiz" in r.text
    assert 'href="/users"' not in r.text and "Log out" not in r.text  # no admin nav


def test_staff_quiz_is_recorded_against_the_person(client, anon, session_factory):
    uid, token = _drill_token(client, session_factory)
    module, qs = _module_and_questions(session_factory)
    r = anon.post(f"/t/training/{token}/{module.slug}/quiz",
                  data={f"q{q.id}": str(q.correct_index) for q in qs})
    assert r.status_code == 200 and "Passed" in r.text
    assert f'action="/t/training/{token}/{module.slug}/quiz"' not in r.text  # result view
    with session_factory() as s:
        result = s.exec(select(QuizResult)).one()
    assert result.user_id == uid and result.token == token and result.score == len(qs)


def test_staff_training_rejects_unknown_token(anon, session_factory):
    module, qs = _module_and_questions(session_factory)
    assert anon.get(f"/t/training/nope/{module.slug}").status_code == 404
    r = anon.post(f"/t/training/nope/{module.slug}/quiz", data={})
    assert r.status_code == 404
    with session_factory() as s:
        assert not s.exec(select(QuizResult)).all()


def test_admin_training_preview_still_requires_login(anon, session_factory):
    module, _ = _module_and_questions(session_factory)
    r = anon.get(f"/training/{module.slug}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def _module(session_factory, slug):
    with session_factory() as s:
        m = s.exec(select(TrainingModule).where(TrainingModule.slug == slug)).one()
        qs = s.exec(select(TrainingQuestion).where(TrainingQuestion.module_id == m.id)
                    .order_by(TrainingQuestion.order)).all()
    return m, qs


def test_each_cisa_video_is_a_module_with_a_quiz(session_factory):
    with session_factory() as s:
        videos = [m for m in s.exec(select(TrainingModule)).all() if m.video_url]
    yt = [m for m in videos if "youtube.com" in m.video_url]
    assert len(yt) == 5
    for m in yt:
        _, qs = _module(session_factory, m.slug)
        assert len(qs) >= 3
        assert all(0 <= q.correct_index < len(q.choices) for q in qs)


def test_video_lesson_embeds_youtube(client):
    r = client.get("/training/video-strong-passwords")
    assert "https://www.youtube.com/embed/XXrbut5xRbE" in r.text
    # YouTube needs a Referer to play embeds (Error 153 under no-referrer).
    assert 'referrerpolicy="strict-origin-when-cross-origin"' in r.text
    assert "Watch the video above" in r.text


def test_pass_and_fail_against_pass_mark(client, session_factory):
    m, qs = _module(session_factory, "video-turn-on-mfa")
    all_right = {f"q{q.id}": str(q.correct_index) for q in qs}
    r = client.post(f"/training/{m.slug}/quiz", data=all_right)
    assert "Passed" in r.text
    one_wrong = dict(all_right, **{f"q{qs[0].id}": str((qs[0].correct_index + 1) % 4)})
    r = client.post(f"/training/{m.slug}/quiz", data=one_wrong)   # 2/3 = 67% < 80%
    assert "Not passed yet" in r.text


def test_staff_progress_shows_completed_person(client, session_factory):
    client.post("/users", data={"email": "done@example.com", "name": "Done Person",
                                "consented": "on"})
    client.post("/campaigns", data={"name": "C", "subject": "S",
                                    "from_name": "IT", "from_email": "it@example.com"})
    from app.models import Campaign, User
    with session_factory() as s:
        uid = s.exec(select(User.id)).first()
        cid = s.exec(select(Campaign.id)).first()
        slugs = [m.slug for m in s.exec(select(TrainingModule)).all()]
    client.post(f"/campaigns/{cid}/targets", data={"user_ids": uid})
    with session_factory() as s:
        token = s.exec(select(Target.token)).first()

    for slug in slugs[:-1]:
        _, qs = _module(session_factory, slug)
        client.post(f"/t/training/{token}/{slug}/quiz",
                    data={f"q{q.id}": str(q.correct_index) for q in qs})
    page = client.get("/training").text
    assert "Done Person" in page and "In progress" in page

    _, qs = _module(session_factory, slugs[-1])
    client.post(f"/t/training/{token}/{slugs[-1]}/quiz",
                data={f"q{q.id}": str(q.correct_index) for q in qs})
    assert "Training complete" in client.get("/training").text


def test_new_seed_modules_reach_existing_database(session_factory):
    from app.database import _seed_training
    with session_factory() as s:
        m = s.exec(select(TrainingModule).where(TrainingModule.slug == "video-avoid-phishing")).one()
        for q in s.exec(select(TrainingQuestion).where(TrainingQuestion.module_id == m.id)).all():
            s.delete(q)
        s.commit()
        s.delete(m)
        s.commit()
    _seed_training()
    m, qs = _module(session_factory, "video-avoid-phishing")
    assert m.video_url and len(qs) == 3
