"""XSS escaping in email render + CSV formula-injection escaping."""
from sqlmodel import select

from app.mailer import render_email_html
from app.models import Campaign, Target, User


def test_recipient_name_is_html_escaped_in_email():
    campaign = Campaign(name="c", from_name="IT", from_email="it@example.com")
    target = Target(campaign_id=1, user_id=1, email="a@example.com",
                    name="<script>alert(1)</script>", token="tok", consented=True)
    out = render_email_html(campaign, target, preview=True)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_csv_export_escapes_formula_injection(client, session_factory):
    client.post("/users", data={"email": "x@example.com", "name": "A", "consented": "on"})
    # Campaign name begins with '=' — a classic CSV formula-injection payload.
    client.post("/campaigns", data={"name": "=cmd|'/c calc'!A1", "subject": "S",
                                    "from_name": "IT", "from_email": "it@example.com"})
    with session_factory() as s:
        uid = s.exec(select(User.id)).first()
        cid = s.exec(select(Campaign.id)).first()
    client.post(f"/campaigns/{cid}/targets", data={"user_ids": uid})
    with session_factory() as s:
        token = s.exec(select(Target.token)).first()
    client.get(f"/t/open/{token}.png")  # create an event so a row exists

    body = client.get("/reports/export.csv").text
    assert "'=cmd" in body        # escaped with a leading quote
    assert ",=cmd" not in body    # never a raw formula cell
