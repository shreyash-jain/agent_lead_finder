"""Shared helpers for enrichers: fetch a website's homepage + likely contact pages."""
import re
import time
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "Mozilla/5.0 (compatible; VacademyLeadBot/1.0; +mailto:research@vacademy.io)"
TIMEOUT = 6
SLEEP_BETWEEN_PAGES = 0.2
CONTACT_PATHS = ["", "/contact", "/contact-us", "/about"]


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    return url


def fetch_site_pages(url: str, max_pages: int = 3) -> dict[str, str]:
    """Fetch homepage + up to `max_pages-1` contact-style pages. Returns {url: html}."""
    url = _normalize_url(url)
    if not url:
        return {}

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    headers = {"User-Agent": USER_AGENT}
    pages: dict[str, str] = {}

    candidates = [urljoin(base, p) for p in CONTACT_PATHS]

    for candidate in candidates:
        if len(pages) >= max_pages:
            break
        try:
            resp = requests.get(candidate, headers=headers, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code == 200 and resp.text:
                pages[candidate] = resp.text
        except requests.RequestException:
            pass
        time.sleep(SLEEP_BETWEEN_PAGES)

    return pages


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def html_to_text(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html)
    return _WHITESPACE_RE.sub(" ", text)
