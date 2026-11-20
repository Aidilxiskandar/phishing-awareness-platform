"""Smoke tests: every admin page renders (empty DB) for a logged-in admin."""
import pytest

PAGES = ["/", "/phishing", "/users", "/training", "/reports"]


@pytest.mark.parametrize("path", PAGES)
def test_page_renders_empty(client, path):
    r = client.get(path)
    assert r.status_code == 200, path


@pytest.mark.parametrize("path", PAGES)
def test_page_renders_with_data(client, path):
    # Seed a little data, then confirm pages still render (chart math on real rows).
    client.post("/users", data={"email": "a@example.com", "name": "Alice", "consented": "on"})
    client.post("/campaigns", data={"name": "Drill", "subject": "Verify",
                                    "from_name": "IT", "from_email": "it@example.com"})
    r = client.get(path)
    assert r.status_code == 200, path
