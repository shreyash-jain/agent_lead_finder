"""Stage 2: read plan.json -> call Serper for each NEW query -> append to raw/<timestamp>.jsonl.

Skips queries already in state.search.executed_queries so re-running after adding new
queries to plan.json only hits Serper for the new ones.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from src.campaign import Campaign, mark_stage_done, query_dedupe_key

SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_MAPS_URL = "https://google.serper.dev/maps"
SLEEP_BETWEEN_REQUESTS = 0.5


def call_serper(api_key: str, query: dict) -> dict | None:
    url = SERPER_MAPS_URL if query["type"] == "maps" else SERPER_SEARCH_URL
    payload = {"q": query["query"]}
    if query["type"] == "maps" and query.get("location"):
        payload["location"] = query["location"]
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = 2 ** attempt
                print(f"    HTTP {resp.status_code}, retry in {wait}s")
                time.sleep(wait)
                continue
            print(f"    HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        except requests.RequestException as e:
            print(f"    Request error: {e}")
            time.sleep(2 ** attempt)
    return None


def extract_results(query: dict, response: dict) -> list[dict]:
    if query["type"] == "maps":
        return response.get("places", [])
    return response.get("organic", [])


def run(campaign: Campaign) -> None:
    load_dotenv()
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        print("SERPER_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    if not campaign.plan_path.exists():
        print(f"Plan not found: {campaign.plan_path} — run 'plan' first.", file=sys.stderr)
        sys.exit(1)

    plan = json.loads(campaign.plan_path.read_text())
    all_queries = plan["queries"]

    state = campaign.load_state()
    executed = set(state["stages"]["search"]["executed_queries"])

    pending = [
        q for q in all_queries
        if query_dedupe_key(q["type"], q["query"], q.get("location")) not in executed
    ]

    if not pending:
        print(f"All {len(all_queries)} queries in plan.json already executed. Nothing to do.")
        print("Add new queries to plan.json (or run 'plan' again to regenerate) and re-run search.")
        return

    if len(pending) < len(all_queries):
        skipped = len(all_queries) - len(pending)
        print(f"Skipping {skipped} already-executed queries; running {len(pending)} new ones.\n")

    campaign.init_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = campaign.raw_dir / f"{ts}.jsonl"
    print(f"Output: {out_path}\n")

    total_results = 0
    failed = 0
    just_executed: list[str] = []

    with out_path.open("w") as f:
        for i, query in enumerate(pending, 1):
            label = f"[{i}/{len(pending)}] {query['type']:6s}  {query['query']!r}"
            if query.get("location"):
                label += f" @ {query['location']}"
            print(label, flush=True)

            response = call_serper(api_key, query)
            if response is None:
                failed += 1
                time.sleep(SLEEP_BETWEEN_REQUESTS)
                continue

            results = extract_results(query, response)
            print(f"    -> {len(results)} results", flush=True)
            total_results += len(results)

            for result in results:
                f.write(json.dumps({
                    "source_type": query["type"],
                    "source_query": query["query"],
                    "source_location": query.get("location"),
                    "segment": query["segment"],
                    "intent": query["intent"],
                    "result": result,
                }) + "\n")

            just_executed.append(query_dedupe_key(query["type"], query["query"], query.get("location")))
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    # Persist what we ran
    state["stages"]["search"]["executed_queries"] = sorted(executed | set(just_executed))
    mark_stage_done(state, "search", queries_run=len(just_executed), results=total_results, failed=failed)
    campaign.save_state(state)

    print(f"\nDone. {total_results} raw results from {len(just_executed)} new queries ({failed} failed)")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.search <campaign_slug>", file=sys.stderr)
        sys.exit(1)
    run(Campaign(slug=sys.argv[1]))
