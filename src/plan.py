"""Stage 1: read campaign brief markdown -> ask Claude to produce plan.json.

Requires ANTHROPIC_API_KEY. If you don't have one, see AGENT.md for the
"paste the brief into Claude/ChatGPT" alternative path.
"""
import sys
from typing import Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.campaign import Campaign, mark_stage_done


class SerperQuery(BaseModel):
    type: Literal["search", "maps"] = Field(
        description='"search" for Serper /search (Google web), "maps" for Serper /maps (Google Maps listings).'
    )
    query: str = Field(description="The exact query string to send to Serper.")
    location: str | None = Field(
        default=None,
        description='For "maps" queries: the city anchor, e.g. "Doha, Qatar". Null for "search" queries.',
    )
    segment: str = Field(description="Which subsegment from the brief this query targets.")
    intent: str = Field(description="One-sentence explanation of what this query is meant to find.")


class SearchPlan(BaseModel):
    brief_slug: str
    queries: list[SerperQuery]


SYSTEM_PROMPT = """You are a lead-generation search strategist.

You will be given a brief that describes who we want to find (a target segment of companies/orgs/people). Your job is to produce a concrete list of Serper queries — a mix of Google web search ("search") and Google Maps queries ("maps") — that will surface those targets.

Rules:
- Cover every in-scope subsegment in the brief. Don't skip any.
- For each subsegment, generate both "search" and "maps" queries (one maps query per city anchor that makes sense for that subsegment).
- Keep queries SHORT and SPECIFIC. Long queries return nothing. Aim for 3-7 words.
- Use natural phrasing a real person would type. No quotes, no site: operators, no boolean OR.
- For "maps" queries, the location field is the city anchor (e.g. "Doha, Qatar"). The query string is the business type only (e.g. "coding academy" not "coding academy in Doha").
- For "search" queries, location is null and any geographic scoping goes in the query string.
- DO NOT include disqualifiers in queries — those are applied as filters downstream.
- Aim for 25-40 queries total. Enough volume to hit the brief's lead target after dedupe, not so many we waste API credit on overlap.
- Vary phrasing within a subsegment — synonyms catch businesses that one phrasing misses.

Return a SearchPlan with brief_slug (from the brief frontmatter) and the queries array."""


def run(campaign: Campaign) -> None:
    load_dotenv()
    if not campaign.brief_path.exists():
        print(f"Brief not found: {campaign.brief_path}", file=sys.stderr)
        sys.exit(1)

    brief_text = campaign.brief_path.read_text()
    client = anthropic.Anthropic()

    print(f"Planning queries for: {campaign.slug}")
    response = client.messages.parse(
        model="claude-opus-4-7",
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": brief_text}],
        output_format=SearchPlan,
    )
    plan = response.parsed_output

    campaign.init_dirs()
    campaign.plan_path.write_text(plan.model_dump_json(indent=2))

    state = campaign.load_state()
    mark_stage_done(state, "plan", query_count=len(plan.queries))
    campaign.save_state(state)

    by_segment: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for q in plan.queries:
        by_segment[q.segment] = by_segment.get(q.segment, 0) + 1
        by_type[q.type] = by_type.get(q.type, 0) + 1

    print(f"\nWrote {len(plan.queries)} queries to {campaign.plan_path}")
    print(f"\nBy type:    {by_type}")
    print(f"By segment:")
    for seg, n in sorted(by_segment.items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {seg}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.plan <campaign_slug>", file=sys.stderr)
        sys.exit(1)
    run(Campaign(slug=sys.argv[1]))
