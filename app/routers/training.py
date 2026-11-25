"""Training tab (admin preview + completion) and the public staff training flow."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import (
    HTMLResponse,
)
from sqlmodel import select

from app.config import settings
from app.database import get_session
from app.models import (
    QuizResult,
    Target,
    TrainingModule,
    TrainingQuestion,
    User,
)
from app.services.video import video_info as _video_info
from app.web import templates

router = APIRouter()


def _passed(score: int, total: int) -> bool:
    """A quiz attempt passes when it meets the configured pass mark."""
    return bool(total) and score * 100 >= settings.training_pass_percent * total


@router.get("/training", response_class=HTMLResponse)
def training_list(request: Request):
    with get_session() as session:
        modules = session.exec(select(TrainingModule).order_by(TrainingModule.order)).all()
        results = session.exec(select(QuizResult).order_by(QuizResult.id.desc())).all()
        module_by_id = {m.id: m for m in modules}
        done = len(results)
        passed = sum(1 for r in results if _passed(r.score, r.total))
        # Per-module pass counts, and per-person progress (attempts linked via token).
        module_passes: dict[int, set] = {m.id: set() for m in modules}
        person_passed: dict[int, set] = {}
        person_tried: dict[int, set] = {}
        for r in results:
            key = r.user_id if r.user_id is not None else f"anon-{r.id}"
            if _passed(r.score, r.total) and r.module_id in module_passes:
                module_passes[r.module_id].add(key)
            if r.user_id is not None:
                person_tried.setdefault(r.user_id, set()).add(r.module_id)
                if _passed(r.score, r.total):
                    person_passed.setdefault(r.user_id, set()).add(r.module_id)
        users = {u.id: u for u in session.exec(
            select(User).where(User.id.in_(list(person_tried)), User.erased_at.is_(None))).all()} if person_tried else {}
        module_ids = set(module_by_id)
        progress = sorted(
            ({"user": users[uid],
              "passed": len(person_passed.get(uid, set()) & module_ids),
              "tried": len(tried & module_ids)}
             for uid, tried in person_tried.items() if uid in users),
            key=lambda row: (-row["passed"], row["user"].email),
        )
    return templates.TemplateResponse(request, "training_list.html", {
        "tab": "training", "modules": modules, "results": results[:15],
        "module_by_id": module_by_id, "done": done, "passed": passed,
        "module_passes": {mid: len(v) for mid, v in module_passes.items()},
        "progress": progress, "pass_percent": settings.training_pass_percent,
        "passed_fn": _passed, "dry_run": settings.dry_run,
    })


def _training_page(request: Request, slug: str, *, target: Target | None,
                   form=None):
    """Render a training module, and grade + record its quiz when `form` is given.

    Two audiences share this page:
      * admins preview modules at /training/{slug} (inside the admin app);
      * staff arrive from a drill's landing page at /t/training/{token}/{slug}.
        That path is public (recipients have no admin login), so it only works
        with a real drill token and never shows admin navigation.
    """
    staff = target is not None
    token = target.token if staff else ""
    with get_session() as session:
        module = session.exec(select(TrainingModule).where(TrainingModule.slug == slug)).first()
        if not module:
            return HTMLResponse("Module not found", status_code=404)
        questions = session.exec(
            select(TrainingQuestion).where(TrainingQuestion.module_id == module.id)
            .order_by(TrainingQuestion.order)
        ).all()
        result = None
        if form is not None:
            score = 0
            for q in questions:
                answer = form.get(f"q{q.id}")
                if isinstance(answer, str) and answer.isdigit() and int(answer) == q.correct_index:
                    score += 1
            session.add(QuizResult(module_id=module.id, token=token,
                                   user_id=target.user_id if staff else None,
                                   score=score, total=len(questions)))
            session.commit()
            result = {"score": score, "total": len(questions),
                      "passed": _passed(score, len(questions)),
                      "pass_percent": settings.training_pass_percent}
        bullets = [b for b in module.body.split("\n") if b.strip()]
        video = _video_info(module)
    base = f"/t/training/{token}" if staff else "/training"
    return templates.TemplateResponse(request, "training_detail.html", {
        "tab": "training", "module": module, "questions": questions,
        "bullets": bullets, "video": video, "result": result,
        "staff": staff, "train_base": base, "dry_run": settings.dry_run,
    })


def _find_target(token: str) -> Target | None:
    with get_session() as session:
        return session.exec(select(Target).where(Target.token == token)).first()


@router.get("/training/{slug}", response_class=HTMLResponse)
def training_detail(request: Request, slug: str):
    return _training_page(request, slug, target=None)


@router.post("/training/{slug}/quiz", response_class=HTMLResponse)
async def submit_quiz(request: Request, slug: str):
    return _training_page(request, slug, target=None, form=await request.form())


@router.get("/t/training/{token}/{slug}", response_class=HTMLResponse)
def staff_training(request: Request, token: str, slug: str):
    target = _find_target(token)
    if not target:
        return HTMLResponse("This training link is not valid.", status_code=404)
    return _training_page(request, slug, target=target)


@router.post("/t/training/{token}/{slug}/quiz", response_class=HTMLResponse)
async def staff_submit_quiz(request: Request, token: str, slug: str):
    target = _find_target(token)
    if not target:
        return HTMLResponse("This training link is not valid.", status_code=404)
    return _training_page(request, slug, target=target, form=await request.form())
