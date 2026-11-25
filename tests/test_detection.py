"""Tests for the click-accuracy engine.

These cover the exact dispute from the internship: a scanner click must not be
counted as a human click, and a real browser (JS confirm) must be.
"""

from app.detection import (
    ClickSignals,
    classify,
)

CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def test_js_confirm_is_human():
    r = classify(ClickSignals(user_agent=CHROME, js_confirmed=True))
    assert r.verdict == "human"
    assert r.confidence >= 0.9


def test_known_scanner_user_agent_is_scanner():
    r = classify(ClickSignals(user_agent="BarracudaCentral/2.0"))
    assert r.verdict == "scanner"


def test_microsoft_safelinks_is_scanner():
    r = classify(ClickSignals(user_agent="Mozilla/5.0 SafeLinks"))
    assert r.verdict == "scanner"


def test_scripting_library_is_scanner():
    assert classify(ClickSignals(user_agent="python-requests/2.31.0")).verdict == "scanner"
    assert classify(ClickSignals(user_agent="curl/8.4.0")).verdict == "scanner"


def test_head_request_is_scanner():
    r = classify(ClickSignals(user_agent=CHROME, http_method="HEAD"))
    assert r.verdict == "scanner"


def test_empty_user_agent_is_scanner():
    assert classify(ClickSignals(user_agent="")).verdict == "scanner"


def test_prefetch_header_is_scanner():
    r = classify(ClickSignals(user_agent=CHROME, headers={"sec-purpose": "prefetch"}))
    assert r.verdict == "scanner"


def test_fast_click_no_confirm_is_unknown():
    # Looks like a browser but arrived within the scan window and has not yet
    # confirmed JS -> hold judgement rather than miscount it as human.
    r = classify(ClickSignals(user_agent=CHROME, seconds_since_send=2.0),
                 time_window_seconds=15)
    assert r.verdict == "unknown"


def test_slow_browser_click_is_human():
    r = classify(ClickSignals(user_agent=CHROME, seconds_since_send=120.0),
                 time_window_seconds=15)
    assert r.verdict == "human"


def test_confirm_beats_fast_window():
    # Even a sub-second arrival is human if the browser actually ran our JS.
    r = classify(ClickSignals(user_agent=CHROME, seconds_since_send=0.5, js_confirmed=True),
                 time_window_seconds=15)
    assert r.verdict == "human"
