"""v_marketing CLI — one entry point for everything.

Run with no args for an interactive menu. Run with a subcommand for direct action.

  python -m src                    interactive menu
  python -m src status             one-line summary of every campaign
  python -m src new <slug>         create a new campaign (drops a brief template)
  python -m src plan <slug>        stage 1 — brief.md -> plan.json (needs ANTHROPIC_API_KEY)
  python -m src search <slug>      stage 2 — plan.json -> raw/*.jsonl (skips already-run queries)
  python -m src normalize <slug>   stage 3 — raw/*.jsonl -> leads.csv (merges; idempotent)
  python -m src enrich <slug>      stage 4 — run all three enrichers in priority order
  python -m src continue <slug>    do whatever has new work (search if new queries, normalize if new raw, enrich if empty cells)
  python -m src run-all <slug>     plan -> search -> normalize -> enrich (the full pipeline)
"""
import argparse
import shutil
import sys
from pathlib import Path

from src.campaign import Campaign, has_run, last_run_at

TEMPLATE_BRIEF = Path("templates/brief.md")


# ----------------------------------------------------------------------------
# Status / display

def fmt_campaign_line(c: Campaign) -> str:
    state = c.load_state()
    stats = state.get("stats", {})
    last = state.get("last_activity_at", "never")
    if stats:
        return (f"  {c.slug:30s}  last: {last[:10]}  "
                f"{stats.get('total_leads', 0):4d} leads  "
                f"phone {stats.get('with_phone', 0):3d}  "
                f"email {stats.get('with_email', 0):3d}  "
                f"linkedin {stats.get('with_linkedin', 0):3d}")
    return f"  {c.slug:30s}  not yet run"


def cmd_status() -> None:
    campaigns = Campaign.list_all()
    if not campaigns:
        print("No campaigns yet. Run 'python -m src new <slug>' to start one.")
        return
    print(f"\n{len(campaigns)} campaign(s):\n")
    for c in campaigns:
        print(fmt_campaign_line(c))
    print()


# ----------------------------------------------------------------------------
# New campaign

def cmd_new(slug: str | None) -> None:
    if not slug:
        slug = input("Slug for the new campaign (e.g. uae_coding): ").strip()
    Campaign.validate_slug(slug)
    c = Campaign(slug=slug)

    if c.exists():
        print(f"Campaign {slug!r} already exists at {c.root}", file=sys.stderr)
        sys.exit(1)

    c.init_dirs()

    if TEMPLATE_BRIEF.exists():
        shutil.copy(TEMPLATE_BRIEF, c.brief_path)
    else:
        c.brief_path.write_text("# Brief: <fill in>\n")

    c.save_state(c.load_state())  # writes initial state.json

    print(f"\nCreated campaign at {c.root}")
    print(f"\nNext step: open {c.brief_path} and fill it in.")
    print(f"Then:  python -m src plan {slug}")
    print(f"(Or, if you don't have ANTHROPIC_API_KEY: see AGENT.md for the manual path.)")


# ----------------------------------------------------------------------------
# Stage dispatch

def _require(c: Campaign) -> None:
    if not c.exists():
        print(f"Campaign {c.slug!r} not found at {c.root}", file=sys.stderr)
        print("Run 'python -m src status' to see existing campaigns.", file=sys.stderr)
        sys.exit(1)


def cmd_plan(slug: str) -> None:
    c = Campaign(slug=slug)
    _require(c)
    from src import plan as plan_module
    plan_module.run(c)


def cmd_search(slug: str) -> None:
    c = Campaign(slug=slug)
    _require(c)
    from src import search as search_module
    search_module.run(c)


def cmd_normalize(slug: str) -> None:
    c = Campaign(slug=slug)
    _require(c)
    from src import normalize as normalize_module
    normalize_module.run(c)


def cmd_enrich(slug: str, only: list[str] | None = None) -> None:
    c = Campaign(slug=slug)
    _require(c)
    enrichers = only or ["phones", "emails", "linkedin"]
    print(f"Running enrichers in order: {', '.join(enrichers)}\n")
    for name in enrichers:
        module_name = f"src.enrich.{name}"
        print(f"=== {module_name} ===")
        module = __import__(module_name, fromlist=["run"])
        module.run(c)
        print()


def cmd_continue(slug: str) -> None:
    """Resume: run whatever stage has new work pending."""
    c = Campaign(slug=slug)
    _require(c)
    state = c.load_state()

    if not has_run(state, "plan"):
        print(f"Plan not yet generated. Next step: python -m src plan {slug}")
        print(f"(Or fill in brief.md and use the manual LLM path from AGENT.md.)")
        return

    # Check for unrun queries
    import json
    plan = json.loads(c.plan_path.read_text())
    from src.campaign import query_dedupe_key
    executed = set(state["stages"]["search"]["executed_queries"])
    pending_queries = [
        q for q in plan["queries"]
        if query_dedupe_key(q["type"], q["query"], q.get("location")) not in executed
    ]

    raw_files = sorted(c.raw_dir.glob("*.jsonl")) if c.raw_dir.exists() else []
    has_raw = bool(raw_files)

    norm_runs = state["stages"]["normalize"].get("runs", [])
    needs_normalize = has_raw and (
        not norm_runs or
        (raw_files and max(p.stat().st_mtime for p in raw_files) > 0 and not c.leads_csv.exists())
    )

    if pending_queries:
        print(f"-> {len(pending_queries)} new queries in plan.json. Running search.")
        cmd_search(slug)
        cmd_normalize(slug)
    elif needs_normalize:
        print("-> Raw data present but not normalized. Running normalize.")
        cmd_normalize(slug)
    elif not c.leads_csv.exists():
        print(f"No leads yet. Next: python -m src search {slug}")
        return

    # Check enrichment gaps
    import csv
    with c.leads_csv.open() as f:
        rows = list(csv.DictReader(f))
    has_unenriched = any(
        r["website"] and (not r["phone"] or not r["email"] or not r["linkedin_url"])
        for r in rows
    )
    if has_unenriched:
        print(f"\n-> {sum(1 for r in rows if r['website'])} leads with websites; some still missing phone/email/linkedin.")
        ans = input("Run enrichment now? [Y/n] ").strip().lower()
        if ans in ("", "y", "yes"):
            cmd_enrich(slug)
    else:
        print("\nNothing else to do. Campaign is fully enriched.")


def cmd_run_all(slug: str) -> None:
    """Plan -> search -> normalize -> enrich. The 'I just want leads' button."""
    c = Campaign(slug=slug)
    _require(c)
    state = c.load_state()
    if not has_run(state, "plan"):
        cmd_plan(slug)
    cmd_search(slug)
    cmd_normalize(slug)
    cmd_enrich(slug)
    print("\n=== Final scorecard ===")
    print(fmt_campaign_line(c))


# ----------------------------------------------------------------------------
# Interactive menu

def interactive() -> None:
    campaigns = Campaign.list_all()
    print()
    if campaigns:
        print(f"{len(campaigns)} campaign(s):\n")
        for c in campaigns:
            print(fmt_campaign_line(c))
        print()
        print("What now?")
        for i, c in enumerate(campaigns, 1):
            print(f"  {i}. Continue {c.slug}")
        print(f"  n. Start a new campaign")
        print(f"  q. Quit")
        choice = input("\n> ").strip().lower()
        if choice == "q" or not choice:
            return
        if choice == "n":
            cmd_new(None)
            return
        if choice.isdigit() and 1 <= int(choice) <= len(campaigns):
            cmd_continue(campaigns[int(choice) - 1].slug)
            return
        print(f"Unrecognized choice: {choice!r}")
    else:
        print("No campaigns yet.\n")
        ans = input("Start one now? [Y/n] ").strip().lower()
        if ans in ("", "y", "yes"):
            cmd_new(None)


# ----------------------------------------------------------------------------
# Argparse wiring

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m src", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="one-line summary of every campaign")

    p_new = sub.add_parser("new", help="create a new campaign")
    p_new.add_argument("slug", nargs="?")

    for name in ("plan", "search", "normalize", "continue", "run-all"):
        p = sub.add_parser(name, help=f"run {name} on the given campaign")
        p.add_argument("slug")

    p_enrich = sub.add_parser("enrich", help="run enrichers (default: all three)")
    p_enrich.add_argument("slug")
    p_enrich.add_argument("--only", help="comma-separated enrichers: phones,emails,linkedin")

    args = parser.parse_args(argv)

    if args.cmd is None:
        interactive()
        return
    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "new":
        cmd_new(args.slug)
    elif args.cmd == "plan":
        cmd_plan(args.slug)
    elif args.cmd == "search":
        cmd_search(args.slug)
    elif args.cmd == "normalize":
        cmd_normalize(args.slug)
    elif args.cmd == "enrich":
        only = [s.strip() for s in args.only.split(",")] if args.only else None
        cmd_enrich(args.slug, only)
    elif args.cmd == "continue":
        cmd_continue(args.slug)
    elif args.cmd == "run-all":
        cmd_run_all(args.slug)


if __name__ == "__main__":
    main()
