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
        "sources": [
            {"kind": "video", "publisher": "CISA", "title": "Recognize and Report Phishing",
             "url": "https://www.youtube.com/watch?v=JlQovysQBn0"},
            {"kind": "video", "publisher": "CISA", "title": "How to Avoid Phishing! (We Can Secure Our World)",
             "url": "https://www.youtube.com/watch?v=sg0kQYvTlnc"},
            {"kind": "guide", "publisher": "CISA", "title": "Recognize and Report Phishing",
             "url": "https://www.cisa.gov/secure-our-world/recognize-and-report-phishing"},
            {"kind": "guide", "publisher": "FTC", "title": "How to Recognize and Avoid Phishing Scams",
             "url": "https://consumer.ftc.gov/articles/how-recognize-and-avoid-phishing-scams"},
            {"kind": "guide", "publisher": "UK NCSC", "title": "Phishing: Spot and report scam emails, texts, websites and calls",
             "url": "https://www.ncsc.gov.uk/collection/phishing-scams"},
        ],
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
            {
                "prompt": "An email comes from it-support@micros0ft.com. What gives it away?",
                "choices": ["Nothing, it's Microsoft's real domain", "The 0 (zero) in place of the letter o: the sender is almost right, but not quite", "It uses lowercase letters", "IT emails always come from Gmail"],
                "correct_index": 1,
            },
            {
                "prompt": "When you're unsure whether an email is real, what does the golden rule say to do?",
                "choices": ["Click, then check", "Stop, check, report", "Reply, wait, delete", "Forward it to everyone"],
                "correct_index": 1,
            },
        ],
    },
    {
        "slug": "password-mfa-safety",
        "title": "Passwords & MFA safety",
        "summary": "Why MFA matters and how attackers try to get around it.",
        "order": 2,
        "sources": [
            {"kind": "video", "publisher": "CISA", "title": "How to Turn on MFA! (We Can Secure Our World)",
             "url": "https://www.youtube.com/watch?v=QWwaidg3AtY"},
            {"kind": "video", "publisher": "CISA", "title": "Make Your Accounts Safer with Multifactor Authentication (MFA)",
             "url": "https://www.youtube.com/watch?v=XIlF2qkav5c"},
            {"kind": "video", "publisher": "CISA", "title": "How to Make Strong Passwords! (We Can Secure Our World)",
             "url": "https://www.youtube.com/watch?v=XXrbut5xRbE"},
            {"kind": "guide", "publisher": "CISA", "title": "More than a Password: multifactor authentication",
             "url": "https://www.cisa.gov/MFA"},
            {"kind": "guide", "publisher": "CISA", "title": "Implementing Number Matching in MFA Applications (fact sheet, PDF)",
             "url": "https://www.cisa.gov/sites/default/files/publications/fact-sheet-implement-number-matching-in-mfa-applications-508c.pdf"},
        ],
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
            {
                "prompt": "Your phone keeps buzzing with login approval requests you didn't start. What is most likely happening?",
                "choices": ["The app has a bug", "Someone has your password and is spamming prompts, hoping you'll approve one to make it stop", "IT is testing the system", "Your phone needs an update"],
                "correct_index": 1,
            },
            {
                "prompt": "During a flood of prompts, a WhatsApp message from 'IT support' says the alerts will stop once you accept one. What should you do?",
                "choices": ["Accept one so the alerts stop", "Reply and ask for their staff ID", "Deny the prompts and report it to IT through a channel you already know", "Turn your phone off until tomorrow"],
                "correct_index": 2,
            },
            {
                "prompt": "Tapping 'Approve' on a login you didn't start is like:",
                "choices": ["Silencing an alarm", "Handing the attacker the key to the door", "Logging yourself out", "Changing your password"],
                "correct_index": 1,
            },
        ],
    },
]


# Video lessons: one official CISA "Secure Our World" video per module, each with
# a short quiz. Lesson points and questions follow the CISA guidance page that
# accompanies each video (cisa.gov/secure-our-world/...).
_CISA_PHISHING = {"kind": "guide", "publisher": "CISA", "title": "Recognize and Report Phishing",
                  "url": "https://www.cisa.gov/secure-our-world/recognize-and-report-phishing"}
_CISA_PASSWORDS = {"kind": "guide", "publisher": "CISA", "title": "Use Strong Passwords",
                   "url": "https://www.cisa.gov/secure-our-world/use-strong-passwords"}
_CISA_MFA = {"kind": "guide", "publisher": "CISA", "title": "Turn On Multifactor Authentication",
             "url": "https://www.cisa.gov/secure-our-world/turn-mfa"}

_VIDEO_MODULES = [
    {
        "slug": "video-recognize-report-phishing",
        "title": "Video: Recognize and report phishing",
        "summary": "CISA video on the three steps: recognize, resist, delete.",
        "order": 3,
        "video_url": "https://www.youtube.com/watch?v=JlQovysQBn0",
        "sources": [_CISA_PHISHING],
        "body": "\n".join([
            "Phishing arrives by email, text, social media message or phone call, dressed up to look like someone you trust.",
            "Recognize: urgent or emotional language, requests for personal or financial details, shortened links, and slightly wrong addresses.",
            "Resist: don't click links or open attachments that seem too good to be true. Report the message instead.",
            "Delete: don't reply, don't click, and don't use 'unsubscribe'. Just delete it.",
        ]),
        "questions": [
            {
                "prompt": "What are CISA's three steps for dealing with a phishing message?",
                "choices": ["Reply, forward, delete", "Recognize, resist, delete", "Open, check, report", "Ignore, archive, forget"],
                "correct_index": 1,
            },
            {
                "prompt": "Which of these is a warning sign of phishing?",
                "choices": ["A message from a colleague you were expecting", "Urgent language warning of bad consequences if you don't act now", "An email with your company's normal signature", "A calendar invite for a team meeting"],
                "correct_index": 1,
            },
            {
                "prompt": "A suspicious email has an 'unsubscribe' link at the bottom. What should you do?",
                "choices": ["Click unsubscribe so it stops", "Reply asking to be removed", "Report it and delete it without clicking anything", "Forward it to friends to warn them"],
                "correct_index": 2,
            },
        ],
    },
    {
        "slug": "video-avoid-phishing",
        "title": "Video: How to avoid phishing",
        "summary": "CISA video on spotting fake messages and checking them safely.",
        "order": 4,
        "video_url": "https://www.youtube.com/watch?v=sg0kQYvTlnc",
        "sources": [_CISA_PHISHING],
        "body": "\n".join([
            "Check the sender and links closely: a fake address can be one letter off (amazan.com instead of amazon.com).",
            "Perfect spelling doesn't mean it's safe: AI-written phishing can have flawless grammar.",
            "If a message might be real, don't use its links or phone numbers. Contact the company through its official website, or the person through a number you already have.",
            "Use the 'report' or 'report spam' option, usually near the sender's name.",
        ]),
        "questions": [
            {
                "prompt": "An email looks like it's from your bank but you're not sure. What's the safest way to check?",
                "choices": ["Call the phone number in the email", "Click the link and see if the page looks real", "Contact the bank using details from its official website or your card", "Reply to the email and ask"],
                "correct_index": 2,
            },
            {
                "prompt": "An email has perfect spelling and grammar. Does that mean it's safe?",
                "choices": ["Yes, scammers always make mistakes", "No, phishing written with AI can have perfect grammar", "Yes, if it has a logo too", "Only if it was sent during work hours"],
                "correct_index": 1,
            },
            {
                "prompt": "Which sender address should make you suspicious?",
                "choices": ["support@amazan.com", "A colleague's usual work address", "Your manager's address in a thread you started", "noreply from a system you just used"],
                "correct_index": 0,
            },
        ],
    },
    {
        "slug": "video-strong-passwords",
        "title": "Video: How to make strong passwords",
        "summary": "CISA video: long, random and unique, plus a password manager.",
        "order": 5,
        "video_url": "https://www.youtube.com/watch?v=XXrbut5xRbE",
        "sources": [_CISA_PASSWORDS],
        "body": "\n".join([
            "Long: at least 16 characters. Longer is stronger.",
            "Random: a mix of letters, numbers and symbols, or a passphrase of 4-7 unrelated words (like HorsePurpleHatRun).",
            "Unique: a different password for every account, so one breach doesn't unlock the rest.",
            "Use a password manager: you only need to remember one strong password.",
            "Avoid birthdays, pet names and simple patterns like 12345.",
        ]),
        "questions": [
            {
                "prompt": "According to CISA, how long should a strong password be?",
                "choices": ["At least 6 characters", "At least 8 characters", "At least 16 characters", "Length doesn't matter"],
                "correct_index": 2,
            },
            {
                "prompt": "Why should every account have a different password?",
                "choices": ["It's required by law", "If one site is breached, attackers can't reuse it to get into your other accounts", "It makes logging in faster", "It stops phishing emails arriving"],
                "correct_index": 1,
            },
            {
                "prompt": "Which of these is the strongest password?",
                "choices": ["Fluffy2019", "12345678", "HorsePurpleHatRunLamp", "Password!"],
                "correct_index": 2,
            },
        ],
    },
    {
        "slug": "video-turn-on-mfa",
        "title": "Video: How to turn on MFA",
        "summary": "CISA video: the three steps to switch on multifactor authentication.",
        "order": 6,
        "video_url": "https://www.youtube.com/watch?v=QWwaidg3AtY",
        "sources": [_CISA_MFA],
        "body": "\n".join([
            "Step 1: open the account's settings and find the security section.",
            "Step 2: turn on MFA. It may be called two-factor or two-step authentication.",
            "Step 3: choose a method: a code by text or email, an authenticator app, or biometrics like a fingerprint.",
            "Turn it on for every account that offers it, starting with email, banking and social media.",
        ]),
        "questions": [
            {
                "prompt": "Where do you usually find the option to turn on MFA?",
                "choices": ["In the account's security settings", "In your email signature", "In the browser history", "It's only available by calling support"],
                "correct_index": 0,
            },
            {
                "prompt": "MFA might appear in settings under which other name?",
                "choices": ["Auto-login", "Two-factor or two-step authentication", "Remember me", "Password hint"],
                "correct_index": 1,
            },
            {
                "prompt": "Which of these is an MFA method?",
                "choices": ["Your username", "A code from an authenticator app", "Your email signature", "A security question about your favourite colour only"],
                "correct_index": 1,
            },
        ],
    },
    {
        "slug": "video-mfa-safer-accounts",
        "title": "Video: Make your accounts safer with MFA",
        "summary": "CISA video on why MFA stops attackers who already have your password.",
        "order": 7,
        "video_url": "https://www.youtube.com/watch?v=XIlF2qkav5c",
        "sources": [_CISA_MFA],
        "body": "\n".join([
            "MFA means proving it's you with more than a password: a code on your phone, an app, or a fingerprint.",
            "Even if a criminal steals your password, they can't get past the second step.",
            "Protect your email first: it's the key to resetting all your other accounts.",
            "Authenticator apps make a new code every 30 seconds.",
        ]),
        "questions": [
            {
                "prompt": "Your password was leaked in a breach, but MFA is on. What happens when an attacker tries to log in?",
                "choices": ["They get in straight away", "They still need the second factor, which they don't have", "Your account is deleted", "MFA turns off automatically"],
                "correct_index": 1,
            },
            {
                "prompt": "Why is it most important to protect your email account with MFA?",
                "choices": ["Email is the most expensive account", "Whoever controls your email can reset passwords for your other accounts", "Email providers require it", "It makes emails arrive faster"],
                "correct_index": 1,
            },
            {
                "prompt": "How often does a typical authenticator app create a new code?",
                "choices": ["Every 30 seconds", "Once a day", "Once a month", "Only when you change your password"],
                "correct_index": 0,
            },
        ],
    },
]

_SEED_MODULES += _VIDEO_MODULES


def _seed_training() -> None:
    from app.models import TrainingModule, TrainingQuestion

    with get_session() as session:
        _backfill_sources(session)
        # Insert any seed module that isn't there yet (by slug), so new lessons
        # also reach databases seeded by an older version.
        have = set(session.exec(select(TrainingModule.slug)).all())
        for m in _SEED_MODULES:
            if m["slug"] in have:
                continue
            module = TrainingModule(slug=m["slug"], title=m["title"],
                                    summary=m["summary"], body=m["body"], order=m["order"],
                                    video_url=m.get("video_url", ""),
                                    sources_json=json.dumps(m.get("sources", [])))
            session.add(module)
            session.commit()
            for i, q in enumerate(m["questions"]):
                session.add(TrainingQuestion(
                    module_id=module.id, prompt=q["prompt"],
                    choices_json=json.dumps(q["choices"]),
                    correct_index=q["correct_index"], order=i,
                ))
        session.commit()


def _backfill_sources(session: Session) -> None:
    """Give modules seeded before sources existed their default reading list.
    Idempotent: only touches seeded modules whose sources are still empty, so an
    admin's own edits are never overwritten."""
    from app.models import TrainingModule

    defaults = {m["slug"]: m.get("sources", []) for m in _SEED_MODULES}
    changed = False
    for module in session.exec(select(TrainingModule)).all():
        if module.slug in defaults and module.sources_json in ("", "[]"):
            module.sources_json = json.dumps(defaults[module.slug])
            session.add(module)
            changed = True
    if changed:
        session.commit()
