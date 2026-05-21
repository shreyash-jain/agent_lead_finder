"""Stage 3: flatten ALL raw jsonl files into a deduped leads.csv.

Merges with the existing leads.csv if present — enriched columns (phone, email, etc.) are
preserved on existing rows; new raw results add new rows or fill empty cells on existing ones.
Re-running is idempotent.
"""
import csv
import json
import re
import shutil
import sys
from urllib.parse import urlparse

from src.campaign import Campaign, mark_stage_done

QATAR_CITIES = ["Doha", "Al Rayyan", "Lusail", "Al Wakrah", "Al Khor"]
QATAR_PHONE_RE = re.compile(r"\+?974[\s\-]?\d{4}[\s\-]?\d{4}")

COLUMNS = [
    "name", "website", "segment", "city", "country",
    "phone", "whatsapp", "email", "linkedin_url",
    "address", "rating", "place_id",
    "source_type", "source_query", "raw_title", "raw_snippet",
    "confidence_score", "notes",
    "status", "last_contacted_at", "channel", "message_id",
]


def normalize_website(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = (parsed.netloc or parsed.path).lower().strip("/")
    if host.startswith("www."):
        host = host[4:]
    return host


def extract_city(address: str | None) -> str:
    if not address:
        return ""
    for city in QATAR_CITIES:
        if city.lower() in address.lower():
            return city
    return ""


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    match = QATAR_PHONE_RE.search(phone)
    if match:
        digits = re.sub(r"\D", "", match.group())
        if digits.startswith("974"):
            digits = digits[3:]
        if len(digits) == 8:
            return f"+974 {digits[:4]} {digits[4:]}"
    return phone.strip()


def row_from_maps_result(raw: dict) -> dict:
    result = raw["result"]
    return _empty_row() | {
        "name": result.get("title", ""),
        "website": result.get("website", ""),
        "segment": raw["segment"],
        "city": extract_city(result.get("address")) or (raw.get("source_location") or "").split(",")[0],
        "country": "Qatar",
        "phone": normalize_phone(result.get("phoneNumber") or result.get("phone")),
        "address": result.get("address", ""),
        "rating": result.get("rating", ""),
        "place_id": result.get("placeId", ""),
        "source_type": "maps",
        "source_query": raw["source_query"],
        "raw_title": result.get("title", ""),
        "raw_snippet": result.get("type", ""),
    }


def row_from_search_result(raw: dict) -> dict:
    result = raw["result"]
    return _empty_row() | {
        "name": result.get("title", ""),
        "website": result.get("link", ""),
        "segment": raw["segment"],
        "country": "Qatar",
        "source_type": "search",
        "source_query": raw["source_query"],
        "raw_title": result.get("title", ""),
        "raw_snippet": result.get("snippet", ""),
    }


def _empty_row() -> dict:
    return {c: "" for c in COLUMNS}


def dedupe_key(row: dict) -> str:
    normalized = normalize_website(row["website"])
    if normalized:
        return f"web:{normalized}"
    return f"name:{row['name'].strip().lower()}|phone:{row['phone']}"


def merge_rows(existing: dict, new: dict) -> dict:
    """Existing values win unless they're empty. Maps source upgrades a Search-sourced row."""
    merged = dict(existing)
    for col, val in new.items():
        if val and not merged.get(col):
            merged[col] = val
    if new.get("source_type") == "maps" and existing.get("source_type") == "search":
        merged["source_type"] = "maps"
    return merged


def run(campaign: Campaign) -> None:
    if not campaign.raw_dir.exists():
        print(f"No raw dir at {campaign.raw_dir} — run 'search' first.", file=sys.stderr)
        sys.exit(1)

    raw_files = sorted(campaign.raw_dir.glob("*.jsonl"))
    if not raw_files:
        print(f"No raw files in {campaign.raw_dir}.", file=sys.stderr)
        sys.exit(1)

    # Load existing leads (preserves enrichment data)
    leads: dict[str, dict] = {}
    if campaign.leads_csv.exists():
        with campaign.leads_csv.open() as f:
            for row in csv.DictReader(f):
                row = {c: row.get(c, "") for c in COLUMNS}
                leads[dedupe_key(row)] = row
        print(f"Loaded {len(leads)} existing leads from {campaign.leads_csv}")

    total_raw = 0
    new_count = 0
    for path in raw_files:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                total_raw += 1
                if raw["source_type"] == "maps":
                    row = row_from_maps_result(raw)
                else:
                    row = row_from_search_result(raw)
                if not row["name"]:
                    continue

                key = dedupe_key(row)
                if key in leads:
                    leads[key] = merge_rows(leads[key], row)
                else:
                    leads[key] = row
                    new_count += 1

    # Atomic write via backup
    if campaign.leads_csv.exists():
        shutil.copy(campaign.leads_csv, campaign.leads_csv.with_suffix(".csv.bak"))
    with campaign.leads_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in leads.values():
            writer.writerow(row)

    state = campaign.load_state()
    state["stats"] = campaign.update_stats()
    mark_stage_done(state, "normalize", raw_files=len(raw_files), raw_results=total_raw,
                    total_leads=len(leads), new_leads=new_count)
    campaign.save_state(state)

    by_segment: dict[str, int] = {}
    for row in leads.values():
        by_segment[row["segment"]] = by_segment.get(row["segment"], 0) + 1

    print(f"\nRead {total_raw} raw results from {len(raw_files)} file(s)")
    print(f"Total leads now: {len(leads)} ({new_count} new this run)")
    print(f"\nBy segment:")
    for seg, n in sorted(by_segment.items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {seg}")
    print(f"\nWrote {campaign.leads_csv}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.normalize <campaign_slug>", file=sys.stderr)
        sys.exit(1)
    run(Campaign(slug=sys.argv[1]))
