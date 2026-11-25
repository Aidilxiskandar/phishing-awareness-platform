"""Library of drill email templates admins can pick when creating a campaign.

Each entry re-creates a common phishing *lure type* for security-awareness
training only:

* Brands are fictional ("Acme IT", "ParcelGo", ...) and every sender domain uses
  the reserved ``.example`` TLD (RFC 2606), so nothing here impersonates a real
  company's name, logo or domain.
* Bodies are deliberately short, plain-text stubs. The renderer
  (``app.mailer.render_email_html``) escapes the body and appends the single
  call-to-action button, which always points at the platform's per-recipient
  tracking URL (``/t/click/{token}``). A template cannot carry its own links, so
  every drill link is tracked by construction.
* ``red_flags`` are the tells a trainee should have spotted -- the real teaching
  payload. They are copied onto the campaign at creation time, so the teaching
  material survives even if the library changes later.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

DIFFICULTIES = ("easy", "medium", "hard")


@dataclass(frozen=True)
class EmailTemplate:
    slug: str
    name: str
    category: str
    difficulty: str          # easy | medium | hard
    from_name: str
    from_email: str
    subject: str
    body: str                # plain-text stub; blank line = new paragraph
    cta_label: str
    red_flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def red_flags_json(self) -> str:
        return json.dumps(list(self.red_flags))


TEMPLATES: tuple[EmailTemplate, ...] = (
    EmailTemplate(
        slug="fake-invoice",
        name="Overdue invoice",
        category="Finance",
        difficulty="easy",
        from_name="Acme Supplies Billing",
        from_email="billing@acme-supplies-payments.example",
        subject="Invoice #INV-20931 is overdue",
        body=(
            "Our records show invoice #INV-20931 is overdue.\n\n"
            "Please review and settle it using the link below."
        ),
        cta_label="View invoice",
        red_flags=(
            "Unexpected invoice from a supplier you don't recognise or didn't order from.",
            "Pressure wording ('overdue', 'final notice') pushing you to act fast.",
            "Sender domain 'acme-supplies-payments.example' is not the supplier's normal domain.",
            "Generic sign-off with no named contact or phone number.",
            "Payment requested via a link instead of your normal accounts-payable process.",
        ),
    ),
    EmailTemplate(
        slug="password-expiry",
        name="Password expiry",
        category="Credentials",
        difficulty="easy",
        from_name="Acme IT Helpdesk",
        from_email="helpdesk@acme-it-support.example",
        subject="Your password expires in 24 hours",
        body=(
            "Your network password will expire soon.\n\n"
            "Use the link below to review your account before access is locked."
        ),
        cta_label="Review my account",
        red_flags=(
            "Asks you to act on your password via email - real IT never needs it entered from a link.",
            "A 24-hour deadline and a lock-out threat create artificial urgency.",
            "Lookalike sender domain 'acme-it-support.example' instead of your company domain.",
            "Password changes should start from the normal sign-in page, not an email link.",
        ),
    ),
    EmailTemplate(
        slug="parcel-delivery",
        name="Missed parcel delivery",
        category="Delivery",
        difficulty="easy",
        from_name="ParcelGo Delivery",
        from_email="no-reply@parcelgo-tracking.example",
        subject="We missed you - parcel PG-558201 is waiting",
        body=(
            "Our courier tried to deliver parcel PG-558201 but nobody was available.\n\n"
            "Confirm your details using the link below to arrange redelivery."
        ),
        cta_label="Reschedule delivery",
        red_flags=(
            "You weren't expecting a parcel, and there is no sender or contents named.",
            "A small 'redelivery fee' is a classic trick to capture card details.",
            "A short return deadline adds urgency.",
            "No greeting by name - the courier would know who the parcel is for.",
        ),
    ),
    EmailTemplate(
        slug="shared-document",
        name="Shared document",
        category="Collaboration",
        difficulty="medium",
        from_name="DocuShare Notifications",
        from_email="share@docushare-files.example",
        subject="A file was shared with you",
        body=(
            "A colleague has shared a file with you.\n\n"
            "Open the document using the link below. This link expires in 7 days."
        ),
        cta_label="Open document",
        red_flags=(
            "Curiosity bait: a document you weren't expecting, often with a sensitive-sounding name.",
            "The sharer is 'a colleague' - no real name is given.",
            "Asks you to sign in again after clicking - a credential-harvesting pattern.",
            "File-sharing notice from a service your company doesn't use.",
        ),
    ),
    EmailTemplate(
        slug="mfa-signin-alert",
        name="Unusual sign-in alert",
        category="Credentials",
        difficulty="medium",
        from_name="Acme IT Security",
        from_email="security-alerts@acme-secure-login.example",
        subject="Unusual sign-in attempt blocked",
        body=(
            "We blocked a sign-in attempt to your account from an unrecognised device.\n\n"
            "If this wasn't you, review your account using the link below."
        ),
        cta_label="Review activity",
        red_flags=(
            "Fear trigger: an unexpected sign-in from a strange location or an odd time.",
            "May ask you to 're-register your MFA device', which hands over your second factor.",
            "Sender domain 'acme-secure-login.example' is a lookalike, not your company domain.",
            "Real alerts tell you to go to the sign-in page yourself, not to click a link.",
        ),
    ),
    EmailTemplate(
        slug="hr-payroll-update",
        name="Payroll details update",
        category="HR",
        difficulty="medium",
        from_name="Acme People & Payroll",
        from_email="payroll@acme-hr-portal.example",
        subject="Confirm your bank details before the next payroll run",
        body=(
            "We are moving to a new payroll provider.\n\n"
            "Please confirm your details on the new portal using the link below."
        ),
        cta_label="Confirm details",
        red_flags=(
            "Requests bank or salary details - payroll changes should go through verified HR channels.",
            "A payday deadline is used to rush you into acting.",
            "Lookalike domain 'acme-hr-portal.example' rather than your real HR system.",
            "A 'new provider' story explains away anything that looks unfamiliar.",
        ),
    ),
    EmailTemplate(
        slug="it-survey",
        name="IT satisfaction survey",
        category="HR",
        difficulty="hard",
        from_name="Acme IT Service Desk",
        from_email="survey@acme-it-feedback.example",
        subject="2-minute IT survey (win a RM50 voucher)",
        body=(
            "Help us improve IT support with a short, 2-minute survey.\n\n"
            "Completed responses are entered into a prize draw. Start using the link below."
        ),
        cta_label="Start survey",
        red_flags=(
            "A reward ('win a voucher') is used as an incentive to click without thinking.",
            "Low-stakes framing ('just 2 minutes') lowers your guard.",
            "Survey hosted on 'acme-it-feedback.example', not a known internal tool.",
            "A sign-in may be requested to 'claim' the prize - that is the trap.",
        ),
    ),
    EmailTemplate(
        slug="ceo-urgent-request",
        name="Urgent request from the CEO",
        category="Executive",
        difficulty="hard",
        from_name="Jordan Avery (CEO)",
        from_email="j.avery@acme-exec-office.example",
        subject="Quick favour - are you at your desk?",
        body=(
            "I'm tied up in meetings and need a quick favour handled discreetly.\n\n"
            "See the details at the link below and let me know once it's done."
        ),
        cta_label="View details",
        red_flags=(
            "Impersonates a senior leader to pressure you into acting without checking.",
            "Secrecy and urgency ('discreetly', 'quick favour') discourage you from verifying.",
            "Reply-to / sender domain 'acme-exec-office.example' is not the real company domain.",
            "An out-of-band channel (link or reply) is used instead of a known internal process.",
            "Verify any unusual executive request through a separate, trusted channel first.",
        ),
    ),
)


_BY_SLUG = {t.slug: t for t in TEMPLATES}


def get_template(slug: str) -> EmailTemplate | None:
    return _BY_SLUG.get(slug)
