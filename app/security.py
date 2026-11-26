"""Authentication / request-guard helpers.

The admin surface is protected deny-by-default by a single middleware (see
app/main.py): every path that is not explicitly public requires a logged-in
admin session, and every state-changing request must carry a valid,
session-bound CSRF token. Public paths are the tracking endpoints (hit by
recipients), static assets, the health check, and the login/logout routes.

Everything security-relevant that the middleware and routes need lives here so
it can be unit-tested without the web layer:

* constant-time credential check (hash-then-compare, safe for any input)
* session lifecycle: rotate on login (anti-fixation), absolute expiry, and
  server-side revocation on logout
* CSRF: a per-session random token, compared in constant time, plus an
  Origin/Referer same-origin check as defence in depth
* login brute-force throttling (in-process)
* client-IP resolution that only trusts X-Forwarded-For from configured proxies
* security headers incl. a nonce-based Content-Security-Policy

Process-local state (throttle counters, revoked session ids) lives in memory.
That is deliberate for a single-process, self-hosted deployment (the shipped
Dockerfile runs one uvicorn worker). With several workers each keeps its own
counters, so the effective lockout threshold scales with the worker count and a
logout is only revoked in the worker that served it; the absolute session
lifetime (SESSION_MAX_AGE) still bounds any stale cookie.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import threading
import time
from urllib.parse import urlencode, urlparse

from starlette.requests import Request

from app.config import settings

# Paths reachable without an admin session. Everything else is protected.
PUBLIC_PREFIXES = ("/t/", "/static/", "/favicon")
PUBLIC_EXACT = {"/health", "/login", "/logout"}

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}

# Recipient-facing tracking endpoints are hit cross-site by design (email
# clients, the landing-page beacon) and never change admin state, so they are
# exempt from CSRF. Everything else that changes state needs a token.
CSRF_EXEMPT_PREFIXES = ("/t/",)
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"

# Absolute session lifetime: a session (and its cookie) is dead after this,
# however active it was. Also used as the cookie Max-Age.
SESSION_MAX_AGE = 8 * 60 * 60

# Login throttling: after LOGIN_MAX_FAILURES failures within LOGIN_WINDOW
# seconds for the same client IP *or* the same username, further attempts are
# refused for LOGIN_LOCKOUT seconds.
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW = 15 * 60
LOGIN_LOCKOUT = 15 * 60

SESSION_COOKIE = "__Host-phishguard" if settings.is_prod else "phishguard_session"


def is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


# --- credentials -------------------------------------------------------------

def constant_time_equals(a: str, b: str) -> bool:
    """Compare two strings without leaking content or length via timing.

    secrets.compare_digest() raises TypeError for non-ASCII str input (an
    attacker could turn that into a 500) and leaks length; hashing both sides
    first gives fixed-length bytes that are safe to compare for any input.
    """
    da = hashlib.sha256(a.encode("utf-8", "surrogatepass")).digest()
    db = hashlib.sha256(b.encode("utf-8", "surrogatepass")).digest()
    return hmac.compare_digest(da, db)


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time check against the single configured admin credential."""
    expected_pw = settings.effective_admin_password
    if not expected_pw:
        return False  # prod with no password set -> no login possible
    # Evaluate both comparisons unconditionally (no short-circuit timing).
    user_ok = constant_time_equals(username, settings.admin_username)
    pw_ok = constant_time_equals(password, expected_pw)
    return user_ok & pw_ok


# --- login throttling --------------------------------------------------------

class LoginThrottle:
    """In-process brute-force limiter keyed by client IP and by username."""

    def __init__(self, max_failures: int = LOGIN_MAX_FAILURES,
                 window: int = LOGIN_WINDOW, lockout: int = LOGIN_LOCKOUT,
                 per_user: bool = True) -> None:
        # per_user=False (public demo): throttle by IP only, so failed guesses
        # can't lock the shared demo account for everyone.
        self.per_user = per_user
        self.max_failures = max_failures
        self.window = window
        self.lockout = lockout
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def _keys(self, ip: str, username: str) -> list[str]:
        # Usernames are case-folded and length-capped so the dict stays bounded.
        keys = [f"ip:{ip}"]
        if self.per_user:
            keys.append(f"user:{username.strip().casefold()[:128]}")
        return keys

    def retry_after(self, ip: str, username: str, now: float | None = None) -> int:
        """Seconds until a login attempt is allowed again (0 = allowed now)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            wait = 0.0
            for k in self._keys(ip, username):
                until = self._locked_until.get(k, 0.0)
                if until > now:
                    wait = max(wait, until - now)
                elif until:
                    self._locked_until.pop(k, None)
            return int(wait) + (1 if wait else 0)

    def record_failure(self, ip: str, username: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            for k in self._keys(ip, username):
                recent = [t for t in self._failures.get(k, []) if now - t < self.window]
                recent.append(now)
                if len(recent) >= self.max_failures:
                    self._locked_until[k] = now + self.lockout
                    recent = []
                self._failures[k] = recent

    def reset(self, ip: str, username: str) -> None:
        with self._lock:
            for k in self._keys(ip, username):
                self._failures.pop(k, None)
                self._locked_until.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


login_throttle = LoginThrottle(per_user=not settings.demo_mode)


# --- session lifecycle -------------------------------------------------------

_revoked_sids: dict[str, float] = {}   # sid -> wall-clock time it can be forgotten
_revoked_lock = threading.Lock()


def _prune_revoked(now: float) -> None:
    for sid, forget_at in list(_revoked_sids.items()):
        if forget_at <= now:
            _revoked_sids.pop(sid, None)


def start_session(request: Request, username: str) -> None:
    """Begin a fresh authenticated session.

    The old session contents are discarded and a new session id + CSRF token
    are minted, so any pre-login session (or a token an attacker planted)
    cannot be carried across the authentication boundary (session fixation).
    """
    request.session.clear()
    request.session.update({
        "admin": username,
        "sid": secrets.token_urlsafe(24),
        "iat": int(time.time()),
        "csrf": secrets.token_urlsafe(32),
    })


def end_session(request: Request) -> None:
    """Log out: revoke the session id server-side, then clear the cookie.

    Starlette sessions are signed cookies, so clearing alone would leave a
    copied cookie valid until it expires. Revoking the sid kills replays.
    """
    sid = request.session.get("sid")
    if sid:
        now = time.time()
        with _revoked_lock:
            _prune_revoked(now)
            _revoked_sids[sid] = now + SESSION_MAX_AGE
    request.session.clear()


def clear_revocations() -> None:
    with _revoked_lock:
        _revoked_sids.clear()


def is_authenticated(request: Request) -> bool:
    try:
        session = request.session
    except AssertionError:
        # SessionMiddleware not installed (shouldn't happen) -> treat as anonymous.
        return False
    if not session.get("admin"):
        return False
    sid, iat = session.get("sid"), session.get("iat")
    if not sid or not isinstance(iat, int):
        return False
    if time.time() - iat > SESSION_MAX_AGE:
        return False
    with _revoked_lock:
        return sid not in _revoked_sids


# --- CSRF --------------------------------------------------------------------

def get_csrf_token(request: Request) -> str:
    """Return the session's CSRF token, minting one if the session has none."""
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def csrf_required(request: Request) -> bool:
    if request.method not in STATE_CHANGING:
        return False
    return not any(request.url.path.startswith(p) for p in CSRF_EXEMPT_PREFIXES)


def same_origin(request: Request) -> bool:
    """Origin/Referer must match our Host when the browser sends one."""
    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    if origin and origin != "null":
        return urlparse(origin).netloc == host
    if origin == "null":
        return False
    referer = request.headers.get("referer")
    if referer:
        return urlparse(referer).netloc == host
    return True


async def _supplied_csrf_token(request: Request) -> str:
    token = request.headers.get(CSRF_HEADER)
    if token:
        return token
    ctype = request.headers.get("content-type", "")
    if ctype.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
        # Read the body first: BaseHTTPMiddleware caches it and replays it to the
        # route, so the endpoint can still parse the form normally.
        await request.body()
        form = await request.form()
        value = form.get(CSRF_FIELD)
        if isinstance(value, str):
            return value
    return ""


async def csrf_ok(request: Request) -> bool:
    """Validate a state-changing request: same origin AND a matching token."""
    if not same_origin(request):
        return False
    expected = request.session.get("csrf")
    if not expected:
        return False
    supplied = await _supplied_csrf_token(request)
    return bool(supplied) and constant_time_equals(supplied, expected)


# --- redirects ---------------------------------------------------------------

def safe_next(target: str | None) -> str:
    """Prevent open-redirect: only allow local, single-slash paths.

    Rejects scheme-relative (//host), backslash tricks (/\\host, which browsers
    normalise to //host) and any control/whitespace characters.
    """
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"
    if "\\" in target or any(ord(ch) < 0x21 or ord(ch) == 0x7F for ch in target):
        return "/"
    if urlparse(target).netloc:
        return "/"
    return target


def login_redirect_url(path: str) -> str:
    """/login URL that returns the user to `path` afterwards (properly encoded)."""
    return "/login?" + urlencode({"next": safe_next(path)})


# --- client IP ---------------------------------------------------------------

def _parse_networks(spec: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue  # ignore junk entries rather than trusting them
    return nets


def _is_trusted(ip: str, nets) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in nets)


def client_ip(request: Request) -> str:
    """Resolve the client IP, trusting X-Forwarded-For only from configured proxies.

    TRUSTED_PROXIES accepts IPs or CIDRs. When the direct peer is trusted we walk
    X-Forwarded-For from the right (entries appended by our own proxies) and
    return the first address that is *not* a trusted proxy. The left-most entry
    is whatever the client chose to send, so it is never taken on faith.
    """
    peer = request.client.host if request.client else ""
    nets = _parse_networks(settings.trusted_proxies)
    if not nets or not _is_trusted(peer, nets):
        return peer
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",")]
    hops = [h for h in hops if h]
    for hop in reversed(hops):
        try:
            ipaddress.ip_address(hop)
        except ValueError:
            return peer  # malformed chain: fall back to the proxy itself
        if not _is_trusted(hop, nets):
            return hop
    return hops[0] if hops else peer


# --- security headers --------------------------------------------------------

# Hosts the training page may embed videos from (see app/services/video.py).
_FRAME_SOURCES = ("https://www.youtube.com", "https://www.youtube-nocookie.com",
                  "https://player.vimeo.com")

# The interactive API docs load Swagger/ReDoc from a CDN with inline script;
# they are disabled in prod and only exist in dev, so they skip the CSP.
_CSP_SKIP = ("/docs", "/redoc")


def new_csp_nonce() -> str:
    return secrets.token_urlsafe(16)


def _is_raw_email(path: str) -> bool:
    # Rendered phishing-email HTML shown inside a preview iframe:
    #   /campaigns/{cid}/email/{tid}  (a recipient's actual email)
    #   /templates/{slug}/email       (a drill template from the library)
    parts = path.strip("/").split("/")
    if len(parts) == 4 and parts[0] == "campaigns" and parts[2] == "email":
        return True
    return len(parts) == 3 and parts[0] == "templates" and parts[2] == "email"


def security_headers(path: str, nonce: str) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        # same-origin, not no-referrer: under no-referrer browsers send
        # "Origin: null" on every form POST (even same-origin), which the CSRF
        # origin check must reject. same-origin keeps the real Origin on our own
        # forms and still sends nothing to other sites, so tokens in our URLs
        # (/t/..., ?next=) never leak cross-origin.
        "Referrer-Policy": "same-origin",
        "X-Frame-Options": "SAMEORIGIN",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    }
    if settings.is_prod:
        headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if _is_raw_email(path):
        # Email HTML served from our origin: sandbox it so even a rendering bug
        # can never run script with access to the admin session.
        headers["Content-Security-Policy"] = (
            "sandbox; default-src 'none'; img-src 'self' data:; "
            "style-src 'unsafe-inline'; frame-ancestors 'self'")
    elif not path.startswith(_CSP_SKIP):
        headers["Content-Security-Policy"] = "; ".join([
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "media-src 'self'",
            "frame-src 'self' " + " ".join(_FRAME_SOURCES),
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'self'",
        ])
    if not path.startswith(("/static/", "/t/open/")):
        # Admin pages carry PII and evidence: keep them out of shared caches
        # and the browser's back/forward history after logout.
        headers["Cache-Control"] = "no-store"
    return headers


def install_template_globals(env) -> None:
    """Expose csrf_token(request) and csp_nonce(request) to all templates."""
    env.globals["csrf_token"] = get_csrf_token
    env.globals["csp_nonce"] = lambda request: getattr(request.state, "csp_nonce", "")
