"""Click-accuracy engine: tell a real human click from an automated scanner click.

This is the reason the platform exists.

Background (from a real security-awareness programme): a phishing-assessment
vendor reported "1 clicker out of 14 detected clicks" and blamed Outlook / link
scanning, yet 4 people admitted they really clicked. Nobody could cleanly
separate a machine click from a human click, so the whole result came down to
"trust us". This module turns that into evidence.

Design
------
Every click carries raw signals: IP, User-Agent, request headers, HTTP method,
and how long after the email was sent it arrived. Those signals are scored,
never discarded. The decisive human signal is a JavaScript "confirm" beacon
fired by the landing page: security scanners and link-preview bots
overwhelmingly do NOT execute JavaScript, so a confirm is strong proof of a real,
interactive browser.

The one exception is a client that *announces itself* as automation (a scanner
User-Agent, a headless-browser brand, a prefetch header) or comes from a network
the operator has declared to be scanner infrastructure. Sandboxes such as
Defender/Proofpoint detonation run real (headless) browsers that DO execute
JavaScript, so self-declared automation outranks the JS beacon: a known scanner
must never be counted as a human.

`classify()` is a pure function - no DB, no web framework, no network access, no
global configuration - so it is trivial to unit test (see tests/test_detection.py
and tests/fixtures/user_agents.py) and to explain in an interview.
"""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# --- Known automated agents -------------------------------------------------
# Each signature is (family label shown to the analyst, regex). Regexes are
# matched case-insensitively against the User-Agent (never `Via`, see below). They
# are anchored on product tokens (e.g. "curl/" not "curl") so that ordinary
# words inside a real browser UA cannot trigger them. Order matters only for the
# label in the reason: more specific families are listed first (e.g. LinkedInBot
# also contains "Apache-HttpClient").


@dataclass(frozen=True)
class ScannerSignature:
    family: str      # e.g. "Microsoft Defender Safe Links"
    category: str    # email-security | mail-proxy | link-preview | crawler | headless | http-library
    pattern: re.Pattern[str]


def _sig(family: str, category: str, regex: str) -> ScannerSignature:
    return ScannerSignature(family, category, re.compile(regex, re.IGNORECASE))


SCANNER_SIGNATURES: tuple[ScannerSignature, ...] = (
    # --- Email security gateways / link-protection / detonation sandboxes ---
    _sig("Microsoft Defender Safe Links", "email-security",
         r"atp-?safe-?links|safe-?links|microsoft[ -]?defender"),
    _sig("Microsoft Office link/protocol discovery", "email-security",
         r"microsoft office (existence|protocol) discovery|ms-office|msoffice|"
         r"microsoft-webdav-miniredir|microsoft office/\d[^)]*\bmicrosoft outlook"),
    _sig("Microsoft Outlook/Teams link preview", "link-preview",
         r"microsoftpreview|skypeuripreview|bingpreview"),
    _sig("Proofpoint URL Defense", "email-security", r"proofpoint|urldefense"),
    _sig("Mimecast URL Protect", "email-security", r"mimecast"),
    _sig("Barracuda", "email-security", r"barracuda"),
    _sig("Cisco Secure Email / IronPort", "email-security",
         r"ironport|\bcisco[ -]?(secure|esa|umbrella|talos)|\bcisco\b|talos ?intelligence"),
    _sig("Symantec / Broadcom MessageLabs", "email-security", r"symantec|messagelabs|broadcom"),
    _sig("Trend Micro", "email-security", r"trend ?micro"),
    _sig("Sophos", "email-security", r"\bsophos"),
    _sig("Forcepoint", "email-security", r"forcepoint|websense"),
    _sig("Trellix / FireEye", "email-security", r"fireeye|trellix"),
    _sig("Fortinet FortiMail/FortiGuard", "email-security", r"fortimail|fortiguard|fortinet"),
    _sig("Check Point / Avanan", "email-security", r"check ?point|avanan"),
    _sig("Zscaler", "email-security", r"zscaler"),
    _sig("Palo Alto Networks", "email-security", r"palo ?alto|wildfire"),
    _sig("Bitdefender", "email-security", r"bitdefender"),
    _sig("Kaspersky", "email-security", r"kaspersky"),
    _sig("VirusTotal / urlscan", "email-security", r"virustotal|urlscan"),
    # --- Mail-provider proxies & checks ---
    _sig("Google (Gmail image proxy / safety checks)", "mail-proxy",
         r"googleimageproxy|google-safety|google-inspectiontool|google-read-aloud|"
         r"google-pagerenderer|google-structured-data|google-site-verification|"
         r"googleother|google favicon|feedfetcher-google|adsbot-google|"
         r"mediapartners-google|apis-google|appengine-google|googlebot"),
    _sig("Yahoo mail proxy", "mail-proxy", r"yahoomailproxy|yahoo! slurp|yahoocachesystem"),
    _sig("Microsoft push / notification fetcher", "mail-proxy", r"microsoft-wns"),
    # --- Chat / social link-preview bots ---
    _sig("Slack link preview", "link-preview", r"slackbot|slack-imgproxy|slack-linkexpanding"),
    _sig("WhatsApp link preview", "link-preview", r"\bwhatsapp/"),
    _sig("Telegram link preview", "link-preview", r"telegrambot"),
    _sig("LinkedIn link preview", "link-preview", r"linkedinbot"),
    _sig("Facebook / Meta link preview", "link-preview",
         r"facebookexternalhit|\bfacebot|meta-externalagent|meta-externalfetcher"),
    _sig("Twitter / X link preview", "link-preview", r"twitterbot"),
    _sig("Discord link preview", "link-preview", r"discordbot"),
    _sig("LINE link preview", "link-preview", r"\bline-poker"),
    _sig("Embed / unfurl service", "link-preview", r"embedly|iframely|redditbot|pinterestbot"),
    # --- Search / generic crawlers ---
    _sig("Search crawler", "crawler",
         r"bingbot|applebot|duckduckbot|yandex(bot|images|metrika)|baiduspider|"
         r"petalbot|semrushbot|ahrefsbot|\bbot/\d|\bcrawler\b|\bspider\b"),
    # --- Headless / automated browsers ---
    _sig("Headless Chrome", "headless", r"headlesschrome"),
    _sig("PhantomJS", "headless", r"phantomjs"),
    _sig("Puppeteer / Playwright / Selenium", "headless",
         r"puppeteer|playwright|selenium|webdriver|chromedriver|geckodriver"),
    _sig("Other headless browser", "headless",
         r"slimerjs|htmlunit|\bjsdom/|chrome-lighthouse"),
    # --- HTTP libraries & command-line tools (no human behind them) ---
    _sig("python-requests", "http-library", r"python-requests/"),
    _sig("Python HTTP library", "http-library", r"python-urllib|python-httpx|aiohttp/|httpx/"),
    _sig("Go-http-client", "http-library", r"go-http-client/"),
    _sig("curl", "http-library", r"(^|[\s(])curl/"),
    _sig("Wget", "http-library", r"(^|[\s(])wget/"),
    _sig("OkHttp", "http-library", r"okhttp/"),
    _sig("Java HTTP client", "http-library",
         r"(^|[\s(])java/\d|apache-httpclient|jakarta commons-httpclient|java-http-client"),
    _sig("Node.js HTTP library", "http-library", r"\baxios/|node-fetch|undici|\bgot \(|node\.js"),
    _sig("Other scripting HTTP client", "http-library",
         r"libwww-perl|\bscrapy/|postmanruntime|\bhttpie/|ruby|faraday|guzzlehttp|"
         r"\bphp/|winhttp|http_request|powershell|\bhttp\.rb"),
)

# Kept for backwards compatibility with code that inspected the old flat list.
SCANNER_UA_PATTERNS = [s.pattern.pattern for s in SCANNER_SIGNATURES]

# User-Agents that look like a normal interactive browser. Used as a positive
# signal, but NEVER on its own: scanners can and do spoof these, which is exactly
# why the JS confirm beacon is the decisive signal.
BROWSER_UA_HINTS = ["mozilla", "chrome", "safari", "firefox", "edg", "opera"]

# Headers that explicitly announce a prefetch / preview rather than a real visit.
PREFETCH_HEADER_HINTS = {
    "purpose": {"prefetch", "preview"},
    "x-purpose": {"prefetch", "preview"},
    "x-moz": {"prefetch"},
    "sec-purpose": {"prefetch", "prefetch;prerender", "prefetch;anonymous-client-ip"},
}

# Header names that only automation tooling sends.
AUTOMATION_HEADERS = {
    "x-devtools-emulate-network-conditions-client-id": "Chrome DevTools protocol (Puppeteer/headless)",
    "x-playwright": "Playwright",
    "x-selenium": "Selenium",
}

# Obsolete browsers a human almost certainly is not running in 2026, but that
# sandboxes still use as a default disguise. Weak signal -> "unknown", not "scanner".
_OBSOLETE_UA = re.compile(r"msie [2-8]\.|windows nt [45]\.|windows 9[58]", re.IGNORECASE)


# --- Known scanner networks (optional, operator-configured) ------------------
# Some gateways (e.g. a Mimecast or Proofpoint tenant) fetch links from fixed,
# published IP ranges while using a perfectly normal browser User-Agent. An
# operator can declare those ranges so clicks from them are labelled scanner.
#
# Nothing is fetched from the network at runtime and NO ranges are built in:
# vendors change their ranges, and a wrong entry would silently turn real people
# into "scanners". Only list ranges that never carry human traffic (never a
# corporate egress proxy such as Zscaler that your staff browse through).
#
# Config string format (e.g. an env var), comma- or newline-separated:
#     "203.0.113.0/24=Mimecast EU, 198.51.100.7=Proofpoint, 2001:db8::/32"
# The "=label" part is optional and is shown in the verdict reason.


@dataclass(frozen=True)
class ScannerNetwork:
    network: ipaddress.IPv4Network | ipaddress.IPv6Network
    label: str


def parse_scanner_networks(spec: str | Iterable[str] | None) -> tuple[ScannerNetwork, ...]:
    """Parse "cidr[=label], ..." into ScannerNetwork entries. Raises ValueError on bad CIDRs."""
    if not spec:
        return ()
    items = re.split(r"[,\n]", spec) if isinstance(spec, str) else list(spec)
    out: list[ScannerNetwork] = []
    for raw in items:
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        cidr, _, label = item.partition("=")
        net = ipaddress.ip_network(cidr.strip(), strict=False)
        out.append(ScannerNetwork(net, label.strip() or str(net)))
    return tuple(out)


@dataclass
class ClickSignals:
    """Everything we know about a single click, framework-agnostic."""
    user_agent: str = ""
    http_method: str = "GET"
    seconds_since_send: float | None = None
    headers: Mapping[str, str] | None = None  # lower-cased header name -> value
    js_confirmed: bool = False              # landing page JS beacon fired
    ip: str | None = None                   # client IP (after trusted-proxy resolution)


@dataclass
class Classification:
    verdict: str          # "human" | "scanner" | "unknown"  (matches models.Verdict)
    reason: str           # human-readable explanation, shown in the dashboard
    confidence: float     # 0.0 - 1.0


def match_scanner_signature(text: str) -> ScannerSignature | None:
    """Return the first scanner signature found in a User-Agent string, if any."""
    if not text:
        return None
    for sig in SCANNER_SIGNATURES:
        if sig.pattern.search(text):
            return sig
    return None


def _looks_like_browser(ua: str) -> bool:
    low = ua.lower()
    return any(h in low for h in BROWSER_UA_HINTS)


def _prefetch_reason(headers: Mapping[str, str]) -> str | None:
    for name, bad_values in PREFETCH_HEADER_HINTS.items():
        val = headers.get(name)
        if val and val.strip().lower().replace(" ", "") in bad_values:
            return f"request header {name}: {val}"
    return None


def _automation_header_reason(headers: Mapping[str, str]) -> str | None:
    for name, what in AUTOMATION_HEADERS.items():
        if name in headers:
            return f"request header {name} ({what})"
    brands = headers.get("sec-ch-ua", "")
    if "headless" in brands.lower():
        return f"client-hint brand list declares a headless browser (sec-ch-ua: {brands})"
    # The Via header is deliberately NOT used: it names the proxies a request
    # passed through, and staff routinely browse through secure web gateways
    # (Zscaler, Palo Alto, Forcepoint, Blue Coat, ...). Treating those as
    # scanners would turn real human clicks into "scanner" - the exact
    # undercounting this engine exists to prevent.
    sender = headers.get("from", "")
    if sender and re.search(r"bot|crawler|spider", sender, re.IGNORECASE):
        return f"From header identifies a crawler ({sender})"
    return None


def _network_match(ip: str | None, networks: Iterable[ScannerNetwork]) -> ScannerNetwork | None:
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    for entry in networks:
        if addr.version == entry.network.version and addr in entry.network:
            return entry
    return None


def classify(
    signals: ClickSignals,
    time_window_seconds: int = 15,
    scanner_networks: Iterable[ScannerNetwork] = (),
) -> Classification:
    """Classify a click as human, scanner, or unknown.

    Order of evidence (strongest first):
      1. Known scanner User-Agent     -> SCANNER (self-declared automation; beats JS,
                                         since detonation sandboxes do run JS).
      2. Prefetch/preview header      -> SCANNER (self-declared).
      3. Automation header (DevTools, headless client hints, crawler From)
                                      -> SCANNER.
      4. IP in an operator-declared scanner network -> SCANNER.
      5. JS confirm fired             -> HUMAN (scanners don't run JS).
      6. HEAD request                 -> SCANNER (scanners probe, humans GET).
      7. Empty User-Agent             -> SCANNER (real browsers always send one).
      8. Obsolete browser disguise (IE <= 8, Windows XP) -> UNKNOWN.
      9. Click inside the time window with no JS confirm yet -> UNKNOWN (likely a
         scanner pre-fetching the link the instant it arrived, but hold judgement
         until the window passes or a confirm arrives).
     10. Browser-looking UA, no red flags -> HUMAN (lower confidence).
     11. Anything else                -> UNKNOWN.
    """
    ua = (signals.user_agent or "").strip()
    method = (signals.http_method or "GET").upper()
    headers = {k.lower(): v for k, v in (signals.headers or {}).items()}
    js_note = " - JavaScript beacon ignored: automated sandboxes run JS" if signals.js_confirmed else ""

    # 1. Known scanner User-Agent.
    sig = match_scanner_signature(ua)
    if sig:
        return Classification(
            "scanner",
            f"User-Agent identifies {sig.family} ({sig.category}){js_note}",
            0.95 if sig.category != "crawler" else 0.9,
        )

    # 2. Self-declared prefetch/preview.
    pf = _prefetch_reason(headers)
    if pf:
        return Classification("scanner", f"prefetch/preview declared ({pf}){js_note}", 0.95)

    # 3. Automation fingerprints in headers.
    auto = _automation_header_reason(headers)
    if auto:
        return Classification("scanner", f"automation detected: {auto}{js_note}", 0.9)

    # 4. Operator-declared scanner infrastructure.
    net = _network_match(signals.ip, scanner_networks)
    if net:
        return Classification(
            "scanner", f"source IP {signals.ip} is in known scanner range {net.network} ({net.label}){js_note}",
            0.85,
        )

    # 5. Decisive human signal.
    if signals.js_confirmed:
        return Classification("human", "landing page JavaScript executed (interactive browser)", 0.98)

    # 6. HEAD request - probing, not visiting.
    if method == "HEAD":
        return Classification("scanner", "HTTP HEAD request (link probe, not a visit)", 0.85)

    # 7. No User-Agent at all.
    if not ua:
        return Classification("scanner", "empty User-Agent (real browsers always send one)", 0.8)

    # 8. Obsolete browser string - a common sandbox disguise, but not proof.
    if _OBSOLETE_UA.search(ua):
        return Classification(
            "unknown",
            "obsolete browser/OS in User-Agent (IE<=8 / Windows XP), a common sandbox "
            "disguise; no browser confirmation",
            0.4,
        )

    # 9. Arrived suspiciously fast with no browser confirmation yet.
    secs = signals.seconds_since_send
    if secs is not None and secs <= time_window_seconds:
        return Classification(
            "unknown",
            f"click {secs:.1f}s after send with no browser confirmation yet "
            f"(within {time_window_seconds}s window - likely automated pre-scan)",
            0.5,
        )

    # 10. Looks like a browser, no red flags, outside the fast-scan window.
    if _looks_like_browser(ua):
        return Classification("human", "browser User-Agent, no scanner signals, outside fast-scan window", 0.7)

    # 11. Give up cleanly rather than guess.
    return Classification("unknown", "no decisive signal (unrecognised non-browser User-Agent)", 0.3)
