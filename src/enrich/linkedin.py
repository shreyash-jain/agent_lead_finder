"""Stage 4b: find LinkedIn company URL for each lead via Serper search."""
import csv
import os
import re
import shutil
import sys
import time

import requests
from dotenv import load_dotenv

from src.campaign import Campaign, mark_stage_done

SERPER_URL = "https://google.serper.dev/search"
SLEEP = 0.4
LINKEDIN_COMPANY_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|school)/[A-Za-z0-9\-_%]+/?")


def clean_name_for_query(name: str) -> str:
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    name = re.sub(r"\b(?:Qatar|Doha|Lusail|Al Rayyan|Al Wakrah|Al Khor)\b", "", name, flags=re.IGNORECASE)
    return name.strip(" -|,")


def find_linkedin(api_key: str, name: str) -> str:
    cleaned = clean_name_for_query(name)
    if not cleaned:
        return ""
    payload = {"q": f'site:linkedin.com/company "{cleaned}"'}
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    try:
        resp = requests.post(SERPER_URL, json=payload, headers=headers, timeout=20)
        if resp.status_code != 200:
            return ""
        for organic in resp.json().get("organic", []):
            link = organic.get("link", "")
            if LINKEDIN_COMPANY_RE.match(link):
                return link.rstrip("/")
    except requests.RequestException:
        pass
    return ""


def run(campaign: Campaign) -> None:
    load_dotenv()
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        print("SERPER_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    if not campaign.leads_csv.exists():
        print(f"{campaign.leads_csv} not found — run 'normalize' first.", file=sys.stderr)
        sys.exit(1)

    with campaign.leads_csv.open() as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    candidates = [r for r in rows if r["name"] and not r["linkedin_url"]]
    print(f"Looking up LinkedIn for {len(candidates)} leads (~{len(candidates)} Serper credits)\n", flush=True)

    found = 0
    for i, row in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {row['name'][:60]}", flush=True)
        url = find_linkedin(api_key, row["name"])
        if url:
            row["linkedin_url"] = url
            found += 1
            print(f"    + {url}", flush=True)
        time.sleep(SLEEP)

    shutil.copy(campaign.leads_csv, campaign.leads_csv.with_suffix(".csv.bak"))
    with campaign.leads_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    state = campaign.load_state()
    state["stats"] = campaign.update_stats()
    mark_stage_done(state, "enrich.linkedin", scanned=len(candidates), found=found)
    campaign.save_state(state)

    total = sum(1 for r in rows if r["linkedin_url"])
    print(f"\nFound {found} new LinkedIn URLs ({total} total of {len(rows)} leads)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.enrich.linkedin <campaign_slug>", file=sys.stderr)
        sys.exit(1)
    run(Campaign(slug=sys.argv[1]))
