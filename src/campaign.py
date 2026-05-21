"""Campaign = a self-contained lead-research effort. Lives at campaigns/<slug>/.

Each campaign holds its own brief, plan, raw search results, leads CSV, and state file.
state.json is the single source of truth for what's been done — every stage reads it
to skip already-completed work and writes to it after finishing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGNS_DIR = Path("campaigns")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,50}[a-z0-9]$")

EMPTY_STATE = {
    "slug": "",
    "created_at": "",
    "last_activity_at": "",
    "stages": {
        "plan": {"done": False},
        "search": {"runs": [], "executed_queries": []},
        "normalize": {"runs": []},
        "enrich.phones": {"runs": []},
        "enrich.linkedin": {"runs": []},
        "enrich.emails": {"runs": []},
    },
    "stats": {},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def query_dedupe_key(type_: str, query: str, location: str | None) -> str:
    return f"{type_}|{query.strip().lower()}|{(location or '').strip().lower()}"


@dataclass
class Campaign:
    slug: str

    @property
    def root(self) -> Path:
        return CAMPAIGNS_DIR / self.slug

    @property
    def brief_path(self) -> Path:
        return self.root / "brief.md"

    @property
    def plan_path(self) -> Path:
        return self.root / "plan.json"

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def leads_csv(self) -> Path:
        return self.root / "leads.csv"

    def exists(self) -> bool:
        return self.root.is_dir()

    def init_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict:
        if not self.state_path.exists():
            state = json.loads(json.dumps(EMPTY_STATE))
            state["slug"] = self.slug
            state["created_at"] = now_iso()
            return state
        return json.loads(self.state_path.read_text())

    def save_state(self, state: dict) -> None:
        state["last_activity_at"] = now_iso()
        self.state_path.write_text(json.dumps(state, indent=2))

    def update_stats(self) -> dict:
        """Recompute the stats snapshot from leads.csv. Returns the updated stats dict."""
        import csv
        if not self.leads_csv.exists():
            return {}
        with self.leads_csv.open() as f:
            rows = list(csv.DictReader(f))
        stats = {
            "total_leads": len(rows),
            "with_website": sum(1 for r in rows if r.get("website")),
            "with_phone": sum(1 for r in rows if r.get("phone")),
            "with_whatsapp": sum(1 for r in rows if r.get("whatsapp")),
            "with_email": sum(1 for r in rows if r.get("email")),
            "with_linkedin": sum(1 for r in rows if r.get("linkedin_url")),
        }
        return stats

    @classmethod
    def validate_slug(cls, slug: str) -> None:
        if not SLUG_RE.match(slug):
            raise ValueError(
                f"Invalid slug {slug!r}. Use lowercase letters, digits, dashes, underscores "
                f"(3-52 chars, must start and end with alphanumeric)."
            )

    @classmethod
    def list_all(cls) -> list[Campaign]:
        if not CAMPAIGNS_DIR.exists():
            return []
        out = []
        for child in sorted(CAMPAIGNS_DIR.iterdir()):
            if child.is_dir() and (child / "brief.md").exists():
                out.append(cls(slug=child.name))
        return out


# ---- state mutation helpers ----------------------------------------------------

def mark_stage_done(state: dict, stage: str, **info) -> None:
    """Append a run record to a stage. `stages.<stage>.runs` always exists for repeatable stages."""
    s = state["stages"].setdefault(stage, {"runs": []})
    record = {"at": now_iso(), **info}
    if "runs" in s:
        s["runs"].append(record)
    else:
        s.update(record)
        s["done"] = True


def has_run(state: dict, stage: str) -> bool:
    s = state["stages"].get(stage, {})
    if "done" in s:
        return bool(s["done"])
    return bool(s.get("runs"))


def last_run_at(state: dict, stage: str) -> str | None:
    s = state["stages"].get(stage, {})
    if "done_at" in s:
        return s["done_at"]
    runs = s.get("runs", [])
    return runs[-1]["at"] if runs else None
