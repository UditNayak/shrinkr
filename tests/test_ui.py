from app import pages
from tests.helpers import create

BROWSER = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


def test_home_page_has_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == pages.CONTENT_SECURITY_POLICY
    assert "<script>" not in response.text  # inline scripts would be blocked by the CSP


def test_browsers_get_a_page_api_clients_get_json(client):
    page = client.get("/nope123", headers=BROWSER)
    assert page.status_code == 404 and "<h1>Link not found</h1>" in page.text
    api = client.get("/nope123", headers={"Accept": "application/json"})
    assert api.status_code == 404 and api.json() == {"detail": "Short link not found"}


def test_redirects_and_error_pages_are_never_cached(client):
    # A cached "Link disabled" page would outlive re-enabling the link (found by the browser check).
    assert client.get("/nope123", headers=BROWSER).headers["cache-control"] == "no-store"
    link = create(client)
    assert client.get(f"/{link['code']}", follow_redirects=False).headers["cache-control"] == "no-store"
