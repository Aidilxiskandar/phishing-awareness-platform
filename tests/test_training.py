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
    data = {"token": token, **{f"q{q.id}": str(q.correct_index) for q in qs}}
    client.post(f"/training/{module.slug}/quiz", data=data)
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
