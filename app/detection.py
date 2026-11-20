"""Click-accuracy engine: tell a real human click from an automated scanner click.

This is the reason the platform exists.

Background (from a real security-awareness programme): a phishing-assessment
vendor reported "1 clicker out of 14 detected clicks" and blamed Outlook / link
scanning, yet 4 people admitted they really clicked. Nobody could cleanly
separate a machine click from a human click, so the whole result came down to
"trust us". This module turns that into evidence.

Design
------
Every click carries raw signals: IP, User-Agent, HTTP method, and how long after
the email was sent it arrived. Those signals are scored, never discarded. The
decisive human signal is a JavaScript "confirm" beacon fired by the landing page:
security scanners and link-preview bots overwhelmingly do NOT execute JavaScript,
so a confirm is strong proof of a real, interactive browser.

`classify()` is a pure function - no DB, no web framework - so it is trivial to
unit test (see tests/test_detection.py) and to explain in an interview.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Known automated agents -------------------------------------------------
# Email security gateways, link-rewriters, and preview bots that fetch URLs
# without a human ever seeing them. Matched case-insensitively as substrings.
SCANNER_UA_PATTERNS = [
    # Email security gateways / link protection
    "proofpoint", "barracuda", "mimecast", "safelinks", "atpsafelinks",
    "symantec", "messagelabs", "ironport", "cisco", "forcepoint",
    "fireeye", "trendmicro", "microsoftpreview", "bitdefender",
    # Mail-client / provider fetchers & open-proxies
    "googleimageproxy", "yahoomailproxy", "microsoft office", "msoffice",
    "skypeuripreview", "microsoft-wns", "ms-office",
    # Generic crawlers & link-preview bots
    "googlebot", "bingbot", "applebot", "duckduckbot", "yandex",
    "facebookexternalhit", "slackbot", "slack-imgproxy", "twitterbot",
    "telegrambot", "whatsapp", "linkedinbot", "discordbot",
    # Automation / scripting libraries
    "curl", "wget", "python-requests", "python-urllib", "go-http-client",
    "java/", "okhttp", "libwww-perl", "headlesschrome", "phantomjs",
    "axios", "node-fetch", "scrapy", "http_request",
]

# User-Agents that look like a normal interactive browser. Used as a positive
# signal, but NEVER on its own: scanners can and do spoof these, which is exactly
# why the JS confirm beacon is the decisive signal.
BROWSER_UA_HINTS = ["mozilla", "chrome", "safari", "firefox", "edg", "opera"]

# Headers that explicitly announce a prefetch / preview rather than a real visit.
PREFETCH_HEADER_HINTS = {
    "purpose": {"prefetch", "preview"},
    "x-purpose": {"prefetch", "preview"},
    "x-moz": {"prefetch"},
    "sec-purpose": {"prefetch", "prefetch;prerender"},
}


@dataclass
class ClickSignals:
    """Everything we know about a single click, framework-agnostic."""
    user_agent: str = ""
    http_method: str = "GET"
    seconds_since_send: float | None = None
    headers: dict | None = None          # lower-cased header name -> value
    js_confirmed: bool = False              # landing page JS beacon fired


@dataclass
class Classification:
    verdict: str          # "human" | "scanner" | "unknown"  (matches models.Verdict)
    reason: str           # human-readable explanation, shown in the dashboard
    confidence: float     # 0.0 - 1.0


def _match_scanner_ua(ua: str) -> str | None:
    low = ua.lower()
    for pat in SCANNER_UA_PATTERNS:
        if pat in low:
            return pat
    return None


def _looks_like_browser(ua: str) -> bool:
    low = ua.lower()
    return any(h in low for h in BROWSER_UA_HINTS)


def _prefetch_reason(headers: dict | None) -> str | None:
    if not headers:
        return None
    for name, bad_values in PREFETCH_HEADER_HINTS.items():
        val = headers.get(name)
        if val and val.strip().lower() in bad_values:
            return f"request header {name}: {val}"
    return None


def classify(signals: ClickSignals, time_window_seconds: int = 15) -> Classification:
    """Classify a click as human, scanner, or unknown.

    Order of evidence (strongest first):
      1. JS confirm fired            -> HUMAN (scanners don't run JS).
      2. Prefetch/preview header     -> SCANNER (self-declared).
      3. Known scanner User-Agent    -> SCANNER.
      4. HEAD request                -> SCANNER (scanners probe, humans GET).
      5. Empty User-Agent            -> SCANNER (real browsers always send one).
      6. Click inside the time window with no JS confirm yet -> UNKNOWN (likely a
         scanner pre-fetching the link the instant it arrived, but hold judgement
         until the window passes or a confirm arrives).
      7. Browser-looking UA, no red flags -> HUMAN (lower confidence).
      8. Anything else               -> UNKNOWN.
    """
    ua = (signals.user_agent or "").strip()
    method = (signals.http_method or "GET").upper()

    # 1. Decisive human signal.
    if signals.js_confirmed:
        return Classification("human", "landing page JavaScript executed (interactive browser)", 0.98)

    # 2. Self-declared prefetch/preview.
    pf = _prefetch_reason(signals.headers)
    if pf:
        return Classification("scanner", f"prefetch/preview declared ({pf})", 0.95)

    # 3. Known scanner User-Agent.
    hit = _match_scanner_ua(ua)
    if hit:
        return Classification("scanner", f"User-Agent matches known scanner/bot pattern '{hit}'", 0.9)

    # 4. HEAD request - probing, not visiting.
    if method == "HEAD":
        return Classification("scanner", "HTTP HEAD request (link probe, not a visit)", 0.85)

    # 5. No User-Agent at all.
    if not ua:
        return Classification("scanner", "empty User-Agent (real browsers always send one)", 0.8)

    # 6. Arrived suspiciously fast with no browser confirmation yet.
    secs = signals.seconds_since_send
    if secs is not None and secs <= time_window_seconds:
        return Classification(
            "unknown",
            f"click {secs:.1f}s after send with no browser confirmation yet "
            f"(within {time_window_seconds}s window - likely automated pre-scan)",
            0.5,
        )

    # 7. Looks like a browser, no red flags, outside the fast-scan window.
    if _looks_like_browser(ua):
        return Classification("human", "browser User-Agent, no scanner signals, outside fast-scan window", 0.7)

    # 8. Give up cleanly rather than guess.
    return Classification("unknown", "no decisive signal", 0.3)
