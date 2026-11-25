"""Drill email-template library: rendering, tracked links, stored red flags."""
import pytest
from sqlmodel import select

from app.mailer import build_tracking_urls, render_email_html
from app.models import Campaign, Target
from app.services.email_templates import DIFFICULTIES, TEMPLATES, get_template


def test_library_shape():
    assert 6 <= len(TEMPLATES) <= 8
    assert len({t.slug for t in TEMPLATES}) == len(TEMPLATES)
    for t in TEMPLATES:
        assert t.name and t.category and t.subject and t.body and t.cta_label
        assert t.difficulty in DIFFICULTIES
        assert len(t.red_flags) >= 3
        # Fictional brands only: reserved .example TLD, never a real domain.
        assert t.from_email.endswith(".example")
    assert get_template("nope") is None


@pytest.mark.parametrize("tmpl", TEMPLATES, ids=lambda t: t.slug)
def test_template_renders_with_tracked_link(tmpl):
    campaign = Campaign(name="c", body=tmpl.body, cta_label=tmpl.cta_label)
    target = Target(campaign_id=1, user_id=1, email="a@example.com", name="Al", token="tok123")
    html = render_email_html(campaign, target)
    urls = build_tracking_urls("tok123")
    assert f'href="{urls["click"]}"' in html
    assert urls["open_pixel"] in html
    assert tmpl.cta_label in html
    # The only links are the tracked CTA and the per-recipient report link.
    assert html.count("href=") == 2
    assert f'href="{urls["report"]}"' in html
    # Preview is defanged.
    prev = render_email_html(campaign, target, preview=True)
    assert urls["click"] not in prev and urls["open_pixel"] not in prev


def test_body_is_escaped():
    campaign = Campaign(name="c", body='<a href="http://evil">x</a>\n\npara two')
    target = Target(campaign_id=1, user_id=1, email="a@example.com", token="t")
    html = render_email_html(campaign, target)
    assert "http://evil" not in html.replace("&quot;http://evil&quot;", "")
    assert "&lt;a href=" in html and "<p>para two</p>" in html


def test_create_campaign_from_template_stores_red_flags(client, session_factory):
    tmpl = get_template("fake-invoice")
    client.post("/campaigns", data={
        "name": "T", "subject": tmpl.subject, "from_name": tmpl.from_name,
        "from_email": tmpl.from_email, "template_slug": tmpl.slug, "body": ""})
    with session_factory() as s:
        c = s.exec(select(Campaign).where(Campaign.name == "T")).one()
    assert c.template_slug == tmpl.slug
    assert c.red_flags == list(tmpl.red_flags)
    assert c.body == tmpl.body and c.cta_label == tmpl.cta_label


def test_custom_body_overrides_template(client, session_factory):
    client.post("/campaigns", data={
        "name": "X", "subject": "Custom subj", "from_name": "IT",
        "from_email": "it@example.com", "template_slug": "it-survey", "body": "My own text"})
    client.post("/campaigns", data={
        "name": "Plain", "subject": "s", "from_name": "IT", "from_email": "it@example.com"})
    with session_factory() as s:
        c = s.exec(select(Campaign).where(Campaign.name == "X")).one()
        plain = s.exec(select(Campaign).where(Campaign.name == "Plain")).one()
    assert c.body == "My own text" and c.subject == "Custom subj"
    assert c.red_flags  # still snapshotted for teaching
    assert plain.template_slug == "" and plain.red_flags == []


def test_template_preview_pages(client):
    page = client.get("/templates/password-expiry/preview")
    assert page.status_code == 200
    assert "Red flags to teach" in page.text
    assert "/templates/password-expiry/email" in page.text
    raw = client.get("/templates/password-expiry/email")
    assert raw.status_code == 200 and 'href="#"' in raw.text
    assert client.get("/templates/nope/preview").status_code == 404
    assert client.get("/templates/nope/email").status_code == 404


def test_phishing_page_lists_templates(client):
    r = client.get("/phishing")
    assert r.status_code == 200
    for t in TEMPLATES:
        assert t.slug in r.text
