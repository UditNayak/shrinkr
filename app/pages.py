"""HTML responses: security headers for our pages, and friendly error pages for browsers."""

from html import escape

from fastapi.responses import HTMLResponse

# Content Security Policy: the browser may load scripts, styles and images only from this
# server, and runs no inline scripts. Even if HTML were ever injected into a page, it could
# not execute, which protects the management tokens the page keeps in localStorage.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
PAGE_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",  # don't let browsers guess a different file type
}

ERROR_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} · shrinkr</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <main class="error-page">
    <a href="/" class="brand">shrinkr</a>
    <h1>{title}</h1>
    <p class="muted">{message}</p>
    <a class="button primary" href="/">Create a short link</a>
  </main>
</body>
</html>
"""


def wants_html(accept_header: str | None) -> bool:
    """Browsers ask for text/html when following a link; API clients and curl don't."""
    return "text/html" in (accept_header or "")


def error_page(status_code: int, title: str, message: str) -> HTMLResponse:
    html = ERROR_PAGE.format(title=escape(title), message=escape(message))
    # no-store: browsers may otherwise keep a 404/410 and show "disabled" even after the
    # owner re-enables the link (found by the browser test).
    headers = {**PAGE_HEADERS, "Cache-Control": "no-store"}
    return HTMLResponse(html, status_code=status_code, headers=headers)
