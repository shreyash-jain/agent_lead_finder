"""Stage 4c: scrape websites for email addresses."""
import csv
import re
import shutil
import sys
from urllib.parse import urlparse

from src.campaign import Campaign, mark_stage_done
from src.enrich._fetch import fetch_site_pages

MAILTO_RE = re.compile(r'mailto:([^"\'\s>?]+)', re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

JUNK_DOMAINS = {
    "sentry.io", "sentry-next.wixpress.com", "wixpress.com", "googleapis.com",
    "google-analytics.com", "google.com", "facebook.com", "instagram.com",
    "twitter.com", "youtube.com", "linkedin.com", "github.com", "example.com",
    "sentry.wixpress.com", "gstatic.com",
}
JUNK_LOCAL_PARTS = {"noreply", "no-reply", "donotreply", "do-not-reply", "wordpress"}


def is_real_email(email: str) -> bool:
    email = email.lower().strip()
    if "@" not in email:
        return False
    local, _, domain = email.partition("@")
    if local in JUNK_LOCAL_PARTS:
        return False
    if any(domain.endswith(d) for d in JUNK_DOMAINS):
        return False
    if domain.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return False
    return True


def pick_best_email(candidates: list[str], site_domain: str) -> str:
    cleaned = [c.lower().strip() for c in candidates if is_real_email(c)]
    if not cleaned:
        return ""

    seen = []
    for email in cleaned:
        if email not in seen:
            seen.append(email)

    same_domain = [e for e in seen if e.endswith(f"@{site_domain}")]
    pool = same_domain or seen

    priority_prefixes = ["info", "contact", "hello", "admin", "office", "enquiry", "enquiries", "support"]
    for prefix in priority_prefixes:
        for email in pool:
            if email.startswith(f"{prefix}@"):
                return email
    return pool[0]


def site_domain(url: str) -> str:
    if "://" not in url:
        url = "https://" + url
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def run(campaign: Campaign) -> None:
    if not campaign.leads_csv.exists():
        print(f"{campaign.leads_csv} not found — run 'normalize' first.", file=sys.stderr)
        sys.exit(1)

    with campaign.leads_csv.open() as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    candidates = [r for r in rows if r["website"] and not r["email"]]
    print(f"Scanning {len(candidates)} websites for emails\n", flush=True)

    found = 0
    for i, row in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {row['name'][:50]:50s}  {row['website'][:45]}", flush=True)
        pages = fetch_site_pages(row["website"])
        if not pages:
            continue

        all_emails: list[str] = []
        for html in pages.values():
            all_emails.extend(MAILTO_RE.findall(html))
            all_emails.extend(EMAIL_RE.findall(html))

        best = pick_best_email(all_emails, site_domain(row["website"]))
        if best:
            row["email"] = best
            found += 1
            print(f"    + {best}", flush=True)

    shutil.copy(campaign.leads_csv, campaign.leads_csv.with_suffix(".csv.bak"))
    with campaign.leads_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    state = campaign.load_state()
    state["stats"] = campaign.update_stats()
    mark_stage_done(state, "enrich.emails", scanned=len(candidates), found=found)
    campaign.save_state(state)

    total = sum(1 for r in rows if r["email"])
    print(f"\nFound {found} new emails ({total} total of {len(rows)} leads)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.enrich.emails <campaign_slug>", file=sys.stderr)
        sys.exit(1)
    run(Campaign(slug=sys.argv[1]))
