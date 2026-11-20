"""SQLite engine, session helpers, and first-run seed data."""
import json
from pathlib import Path

from sqlalchemy import event, inspect
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings

DB_PATH = Path(__file__).resolve().parent.parent / "phishing.db"
DB_URL = settings.database_url or f"sqlite:///{DB_PATH}"
_is_sqlite = DB_URL.startswith("sqlite")
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)


if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        # WAL lets readers and a writer run concurrently; busy_timeout waits instead
        # of raising "database is locked" when the single writer lock is held.
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def init_db() -> None:
    # Import models so SQLModel registers the tables before create_all.
    from app import models  # noqa: F401

    # Schema ownership:
    #   - Managed deployment: run `alembic upgrade head`; that creates an
    #     alembic_version table. When present, Alembic owns the schema and we do
    #     NOT create_all (avoids clashing with migrations).
    #   - Fresh dev/test DB (no alembic_version): bootstrap the schema directly so
    #     the app runs with zero migration steps.
    if "alembic_version" not in inspect(engine).get_table_names():
        SQLModel.metadata.create_all(engine)
    _seed_training()
    _ensure_demo_video()


def _ensure_demo_video() -> None:
    """Wire the first module to a local video path so the player is demoable.
    Idempotent: only sets it when the module has no video yet."""
    from app.models import TrainingModule
    with get_session() as session:
        m = session.exec(
            select(TrainingModule).where(TrainingModule.slug == "spotting-phishing")
        ).first()
        if m and not m.video_url:
            m.video_url = "/static/videos/spotting-phishing.mp4"
            session.add(m)
            session.commit()


def get_session() -> Session:
    # expire_on_commit=False keeps ORM objects usable after commit(). Without it,
    # attributes read via model_dump() after a commit come back as None because
    # Pydantic reads __dict__ directly and does not trigger SQLAlchemy's reload.
    return Session(engine, expire_on_commit=False)


# --- seed ------------------------------------------------------------------

_SEED_MODULES = [
    {
        "slug": "spotting-phishing",
        "title": "Spotting a phishing email",
        "summary": "The five signals that give a phishing email away.",
        "order": 1,
        "body": "\n".join([
            "Urgency and threats: 'verify within 24 hours or your account is suspended'.",
            "A sender address that looks almost right but isn't (it-support@micros0ft.com).",
            "Links that don't go where they claim - hover to see the real destination first.",
            "Requests for your password, MFA code, or payment details.",
            "Generic greetings and small spelling or grammar slips.",
        ]),
        "questions": [
            {
                "prompt": "An email says your account will be suspended in 2 hours unless you log in via its link. What's the biggest red flag?",
                "choices": ["It has a company logo", "Manufactured urgency and a threat", "It was sent in the morning", "It is addressed to you"],
                "correct_index": 1,
            },
            {
                "prompt": "The safest way to check where a link really goes is to:",
                "choices": ["Click it and see", "Hover over it and read the real URL first", "Forward it to a colleague", "Reply and ask the sender"],
                "correct_index": 1,
            },
            {
                "prompt": "A real IT department will normally never ask you to:",
                "choices": ["Restart your computer", "Reply with your password or MFA code", "Update your software", "Attend a training session"],
                "correct_index": 1,
            },
        ],
    },
    {
        "slug": "password-mfa-safety",
        "title": "Passwords & MFA safety",
        "summary": "Why MFA matters and how attackers try to get around it.",
        "order": 2,
        "body": "\n".join([
            "Use a long, unique password for every account - a password manager makes this easy.",
            "Turn on multi-factor authentication (MFA) everywhere you can.",
            "Never approve an MFA prompt you didn't start - attackers spam prompts hoping you tap 'approve'.",
            "No legitimate service will ask you to read your MFA code to someone.",
            "If you ever enter a password on a page you reached from an email, change it and tell IT.",
        ]),
        "questions": [
            {
                "prompt": "You get an MFA approval prompt on your phone but you didn't try to log in. You should:",
                "choices": ["Approve it to clear the notification", "Deny it and report it to IT", "Ignore it", "Approve it and change your password later"],
                "correct_index": 1,
            },
            {
                "prompt": "The main benefit of MFA is that:",
                "choices": ["Passwords become unnecessary", "A stolen password alone is not enough to log in", "You never have to log in again", "It blocks all phishing emails"],
                "correct_index": 1,
            },
        ],
    },
]


def _seed_training() -> None:
    from app.models import TrainingModule, TrainingQuestion

    with get_session() as session:
        existing = session.exec(select(TrainingModule)).first()
        if existing:
            return
        for m in _SEED_MODULES:
            module = TrainingModule(slug=m["slug"], title=m["title"],
                                    summary=m["summary"], body=m["body"], order=m["order"])
            session.add(module)
            session.commit()
            for i, q in enumerate(m["questions"]):
                session.add(TrainingQuestion(
                    module_id=module.id, prompt=q["prompt"],
                    choices_json=json.dumps(q["choices"]),
                    correct_index=q["correct_index"], order=i,
                ))
        session.commit()
