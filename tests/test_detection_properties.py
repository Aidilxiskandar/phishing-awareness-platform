"""Property-based tests for the click classifier (app/detection.py).

Invariants:
  * any click carrying a known scanner signal is NEVER "human";
  * self-declared automation outranks the JS beacon (sandboxes run JS);
  * a JS-confirmed click from a browser with no automation signal is ALWAYS "human";
  * proxy headers (Via) never turn a real browser click into "scanner";
  * classify() is total (never raises) and deterministic for arbitrary input;
  * the output is always well-formed (known verdict, non-empty reason, 0..1 conf).
"""
import math

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from app.detection import (
    _OBSOLETE_UA,
    PREFETCH_HEADER_HINTS,
    ClickSignals,
    classify,
    match_scanner_signature,
)
from tests.fixtures.user_agents import BROWSER_UAS, SCANNER_UAS

# The autouse DB fixture is function-scoped; it is irrelevant to this pure code.
settings.register_profile(
    "detection", max_examples=300, deadline=None, database=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
props = settings(settings.get_profile("detection"))

VERDICTS = {"human", "scanner", "unknown"}

any_text = st.text(max_size=200)
methods = st.sampled_from(["GET", "HEAD", "POST", "get", "head", "OPTIONS", "", "PUT"]) | any_text
seconds = st.none() | st.floats(allow_nan=True, allow_infinity=True)
header_dicts = st.none() | st.dictionaries(
    st.sampled_from(sorted(PREFETCH_HEADER_HINTS)) | st.text(max_size=20), any_text, max_size=6)
windows = st.integers(min_value=-10, max_value=10_000)


def _random_case(draw, s: str) -> str:
    flips = draw(st.lists(st.booleans(), min_size=len(s), max_size=len(s)))
    return "".join(c.upper() if f else c for c, f in zip(s, flips, strict=True))


def _is_scannerish(ua: str) -> bool:
    return bool(match_scanner_signature(ua) or _OBSOLETE_UA.search(ua))


@st.composite
def scanner_uas(draw):
    """A real-world scanner UA (any case), with arbitrary text appended."""
    ua = draw(st.sampled_from([u for _, u, _ in SCANNER_UAS]))
    return _random_case(draw, ua) + draw(st.sampled_from(["", " ", " extra/1.0"]))


@st.composite
def prefetch_headers(draw):
    name = draw(st.sampled_from(sorted(PREFETCH_HEADER_HINTS)))
    value = draw(st.sampled_from(sorted(PREFETCH_HEADER_HINTS[name])))
    pad = st.sampled_from(["", " ", "  ", "\t"])
    extra = draw(st.dictionaries(st.text(min_size=1, max_size=15).filter(
        lambda k: k not in PREFETCH_HEADER_HINTS), any_text, max_size=4))
    return {**extra, name: draw(pad) + _random_case(draw, value) + draw(pad)}


@st.composite
def signals(draw, **overrides):
    kw = {
        "user_agent": draw(any_text),
        "http_method": draw(methods),
        "seconds_since_send": draw(seconds),
        "headers": draw(header_dicts),
        "js_confirmed": draw(st.booleans()),
    }
    kw.update({k: draw(v) if isinstance(v, st.SearchStrategy) else v
               for k, v in overrides.items()})
    return ClickSignals(**kw)


# --- scanner signals are never "human" -------------------------------------

@props
@given(signals(user_agent=scanner_uas(), js_confirmed=False), windows)
@example(ClickSignals(user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)",
                      seconds_since_send=9999.0), 15)
@example(ClickSignals(user_agent="Mozilla/5.0 HeadlessChrome/120 Safari/537.36",
                      seconds_since_send=9999.0), 15)
def test_known_scanner_ua_is_never_human(sig, window):
    result = classify(sig, window)
    assert result.verdict == "scanner"


@props
@given(signals(headers=prefetch_headers(), js_confirmed=False), windows)
@example(ClickSignals(user_agent="Mozilla/5.0 Chrome/126 Safari/537.36",
                      headers={"sec-purpose": "prefetch;prerender"},
                      seconds_since_send=9999.0), 15)
def test_prefetch_header_is_never_human(sig, window):
    result = classify(sig, window)
    assert result.verdict == "scanner"
    # A stronger signal (a scanner-named UA) may be the one cited instead.
    assert "prefetch" in result.reason or match_scanner_signature(sig.user_agent)


@props
@given(signals(http_method=st.sampled_from(["HEAD", "head", "Head"]), js_confirmed=False),
       windows)
def test_head_request_is_never_human(sig, window):
    assert classify(sig, window).verdict == "scanner"


@props
@given(signals(user_agent=st.text(alphabet=" \t\r\n", max_size=10), js_confirmed=False),
       windows)
def test_empty_or_blank_ua_is_never_human(sig, window):
    assert classify(sig, window).verdict == "scanner"


@props
@given(signals(js_confirmed=False, seconds_since_send=st.floats(-1e6, 15.0)))
def test_inside_scan_window_without_js_is_never_human(sig):
    assert classify(sig, 15).verdict != "human"


# --- JS confirm is decisive ------------------------------------------------

browser_uas = st.sampled_from([u for _, u in BROWSER_UAS])


@props
@given(signals(user_agent=browser_uas, headers=None, js_confirmed=True), windows)
def test_js_confirmed_browser_is_always_human(sig, window):
    result = classify(sig, window)
    assert result.verdict == "human"
    assert result.confidence >= 0.9


@props
@given(signals(user_agent=scanner_uas(), js_confirmed=True), windows)
@example(ClickSignals(user_agent="curl/8", http_method="HEAD",
                      headers={"purpose": "prefetch"}, js_confirmed=True), 15)
def test_self_declared_automation_beats_js_beacon(sig, window):
    # Detonation sandboxes run real headless browsers that DO execute JS.
    assert classify(sig, window).verdict == "scanner"


@props
@given(browser_uas, st.sampled_from([
    "1.1 zscaler", "1.1 ZS-proxy (Zscaler)", "1.1 bluecoat (Symantec)", "1.1 forcepoint",
    "HTTP/1.1 paloalto-proxy", "1.1 FortiGate", "1.1 cisco-umbrella", "1.1 sophos",
]), st.booleans())
def test_corporate_proxy_via_header_never_makes_a_human_a_scanner(ua, via, js):
    # Staff browse through secure web gateways that add a Via header.
    sig = ClickSignals(user_agent=ua, seconds_since_send=3600.0,
                       headers={"via": via}, js_confirmed=js)
    assert classify(sig, 15).verdict == "human"


# --- totality / determinism / well-formedness ------------------------------

@props
@given(signals(), windows)
@example(ClickSignals(user_agent="\x00퟿\U0010ffff", http_method="İ",
                      seconds_since_send=math.nan, headers={}), 0)
@example(ClickSignals(user_agent=None, http_method=None), 15)  # type: ignore[arg-type]
def test_classify_is_total_and_well_formed(sig, window):
    result = classify(sig, window)
    assert result.verdict in VERDICTS
    assert isinstance(result.reason, str) and result.reason
    assert 0.0 <= result.confidence <= 1.0


@props
@given(signals(), windows)
def test_classify_is_deterministic_and_pure(sig, window):
    snapshot = (sig.user_agent, sig.http_method, sig.seconds_since_send,
                dict(sig.headers) if sig.headers is not None else None, sig.js_confirmed)
    first = classify(sig, window)
    assert classify(sig, window) == first
    # The input is not mutated.
    assert (sig.user_agent, sig.http_method, sig.seconds_since_send,
            dict(sig.headers) if sig.headers is not None else None,
            sig.js_confirmed) == snapshot


@props
@given(st.dictionaries(st.text(max_size=30), any_text, max_size=10), windows)
def test_arbitrary_headers_only_promote_to_scanner(headers, window):
    """Adding headers can turn a click into 'scanner' but never into 'human'."""
    base = ClickSignals(user_agent="SomeUnrecognisedAgent/1.0", seconds_since_send=None)
    with_headers = ClickSignals(user_agent=base.user_agent, seconds_since_send=None,
                                headers=headers)
    assert classify(base, window).verdict == "unknown"
    assert classify(with_headers, window).verdict in {"unknown", "scanner"}


@props
@given(st.text(max_size=80), st.floats(min_value=16.0, max_value=1e9))
def test_browser_ua_outside_window_is_human(suffix, secs):
    ua = "Mozilla/5.0 " + suffix
    if _is_scannerish(ua):
        return  # the random suffix happens to name a scanner / obsolete disguise
    result = classify(ClickSignals(user_agent=ua, seconds_since_send=secs), 15)
    assert result.verdict == "human"


@props
@given(st.text(min_size=1, max_size=60).filter(lambda s: s.strip() and not _is_scannerish(s)
    and not any(h in s.lower() for h in ("mozilla", "chrome", "safari", "firefox", "edg", "opera"))))
def test_non_browser_non_scanner_ua_is_unknown(ua):
    result = classify(ClickSignals(user_agent=ua, seconds_since_send=None), 15)
    assert result.verdict == "unknown"
    assert result.reason.startswith("no decisive signal")
