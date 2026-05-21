"""Stage 4a: scrape websites for Qatari phones + WhatsApp links."""
import csv
import re
import shutil
import sys

from src.campaign import Campaign, mark_stage_done
from src.enrich._fetch import fetch_site_pages, html_to_text

QATAR_PHONE_RE = re.compile(r"\+?974[\s\-\.]?\d{4}[\s\-\.]?\d{4}")
WHATSAPP_RE = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send\?(?:[^\"'\s]*&)?phone=)(\+?\d{8,15})",
    re.IGNORECASE,
)


def format_qatar_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("974"):
        digits = digits[3:]
    if len(digits) == 8:
        return f"+974 {digits[:4]} {digits[4:]}"
    return ""


def extract_phone(text: str) -> str:
    match = QATAR_PHONE_RE.search(text)
    if match:
        formatted = format_qatar_phone(match.group())
        if formatted:
            return formatted
    return ""


def extract_whatsapp(html: str) -> str:
    for match in WHATSAPP_RE.finditer(html):
        digits = re.sub(r"\D", "", match.group(1))
        if digits.startswith("974") and len(digits) == 11:
            return f"+974 {digits[3:7]} {digits[7:]}"
        if len(digits) == 8:
            return f"+974 {digits[:4]} {digits[4:]}"
    return ""


def run(campaign: Campaign) -> None:
    if not campaign.leads_csv.exists():
        print(f"{campaign.leads_csv} not found — run 'normalize' first.", file=sys.stderr)
        sys.exit(1)

    with campaign.leads_csv.open() as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    candidates = [r for r in rows if r["website"] and (not r["phone"] or not r["whatsapp"])]
    print(f"Scanning {len(candidates)} websites for phones / WhatsApp\n", flush=True)

    phones_added = 0
    whatsapps_added = 0

    for i, row in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {row['name'][:50]:50s}  {row['website'][:45]}", flush=True)
        pages = fetch_site_pages(row["website"])
        if not pages:
            continue

        combined_html = "\n".join(pages.values())
        combined_text = html_to_text(combined_html)

        if not row["phone"]:
            phone = extract_phone(combined_text)
            if phone:
                row["phone"] = phone
                phones_added += 1
                print(f"    + phone: {phone}", flush=True)

        if not row["whatsapp"]:
            wa = extract_whatsapp(combined_html)
            if wa:
                row["whatsapp"] = wa
                whatsapps_added += 1
                print(f"    + whatsapp: {wa}", flush=True)

    shutil.copy(campaign.leads_csv, campaign.leads_csv.with_suffix(".csv.bak"))
    with campaign.leads_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    state = campaign.load_state()
    state["stats"] = campaign.update_stats()
    mark_stage_done(state, "enrich.phones", scanned=len(candidates),
                    phones_added=phones_added, whatsapps_added=whatsapps_added)
    campaign.save_state(state)

    total_phone = sum(1 for r in rows if r["phone"])
    total_wa = sum(1 for r in rows if r["whatsapp"])
    print(f"\nAdded {phones_added} phones, {whatsapps_added} WhatsApp numbers")
    print(f"Total: {total_phone} with phone, {total_wa} with WhatsApp ({len(rows)} leads)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.enrich.phones <campaign_slug>", file=sys.stderr)
        sys.exit(1)
    run(Campaign(slug=sys.argv[1]))
