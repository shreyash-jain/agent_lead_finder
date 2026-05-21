# AGENT.md — handoff doc for LLMs and devs picking up v_marketing

This document is the single page you can paste into Claude, ChatGPT, or any other LLM to bring it up to speed on this tool. Humans can read it too — it doubles as the "how does this thing work" explainer.

---

## What this tool does

`v_marketing` turns a plain-English description of *who you want to find* (a "brief") into an enriched CSV of B2B leads. The brief is written by a human in markdown. Everything else is automated: it generates search queries, runs them against Serper (Google search + Google Maps), normalizes the results into a CSV, then enriches with phones, emails, and LinkedIn URLs.

The tool is **campaign-based**. One brief = one campaign = one folder under `campaigns/<slug>/`. Campaigns are independent — you can have ten running, none of them touch each other.

---

## The five-second mental model

```
brief.md  →  plan.json  →  raw/*.jsonl  →  leads.csv  →  leads.csv (enriched)
(you write)  (LLM plans)   (Serper runs)  (normalize)   (scrape + Serper)
```

`state.json` in each campaign records what's been done. Every stage reads it to skip completed work and writes to it after running. **Re-running is always safe** — dedupe is built in at every stage.

---

## How to drive the tool when a user comes to you

You'll typically see one of these requests. Use this decision tree.

### "I want to start a new campaign"

1. **Ask the brief-creation interview questions** (see next section). Take notes as the user answers.
2. Run `python -m src new <slug>`. Pick a slug from the user's intent — short, lowercase, underscores. E.g. `qatar_online_edu`, `uk_fintech_startups`, `india_d2c_brands`.
3. Write `campaigns/<slug>/brief.md` from the user's answers. The template is at `templates/brief.md`.
4. Generate `plan.json` (see "two paths" below).
5. Run `python -m src search <slug>` then `python -m src normalize <slug>`.
6. Ask the user if they want enrichment now or later. If yes: `python -m src enrich <slug>`.

### "Continue my campaign" / "Pick up where I left off"

1. Run `python -m src status` to see what exists.
2. Run `python -m src continue <slug>`. It figures out what's next from `state.json`.

### "Add more cities / queries to an existing campaign"

1. Open `campaigns/<slug>/plan.json`.
2. Append new query objects to the `queries` array (keep the same schema as existing ones).
3. Run `python -m src search <slug>` — it only hits Serper for the new queries.
4. Run `python -m src normalize <slug>` to fold new results into the CSV.
5. Run `python -m src enrich <slug>` to enrich the new rows (existing ones are untouched).

### "The leads have noise — out-of-country results, wrong segment, etc."

Open `leads.csv` in Excel/Sheets and inspect. Common issues:
- **Foreign rows leaking in from Serper Maps** — add a country filter in `src/normalize.py` (look at `extract_city` for the pattern).
- **Wrong segment classification** — the segment column comes from whichever query produced the lead; not perfect. Acceptable for v1, improvable with a Claude-based scoring pass.
- **Junk titles (events, news articles, expos)** — these slip in via `/search`. Filter by name keywords or add a Claude-based ICP score stage.

### "Re-enrich the leads — emails missing on a lot of rows"

1. `python -m src enrich <slug> --only emails` — only re-scans rows with empty email. Phones/LinkedIn untouched.

### "Show me what's been done"

`python -m src status` (one-line summary) or open `campaigns/<slug>/state.json` (full audit trail).

---

## The brief-creation interview (use this for any new campaign)

Ask these in order. The user's answers become `brief.md`. Don't ask all at once — batch into 3 rounds.

### Round 1 — the product and the buyer

1. **What does the user's business sell?** One sentence. SaaS? Service? Marketplace?
2. **Who is the actual decision-maker on the buying side?** Owner, head of sales, CTO, marketing director, etc.? This shapes whether we hunt company names or people names.

### Round 2 — the target

3. **Pick one segment per campaign — do not try to cover everything in one brief.** "All B2B" is not a segment; "small fintech startups in the UK" is.
4. **Which 3–5 cities / countries first?** Be specific. Global campaigns are noisy; geography-scoped ones are not.
5. **Size band?** Solo / small (1–10 employees) / mid (10–100) / chains (100+). Pick one. Different bands need different searches.
6. **What does a great lead look like?** Give 2–3 concrete signals. ("Has a website with pricing", "active on LinkedIn", "uses Stripe/Shopify".)
7. **Disqualifiers?** What's *out* of scope? Big players with their own tech teams, individual freelancers, schools, governments, etc.

### Round 3 — scale

8. **Volume target for the first run** — 50 / 200 / 1000? More queries = more Serper credits. Default to 50 for a first run to debug end-to-end cheaply.
9. **One-shot or repeat?** If repeat, the dedupe story matters: re-runs only surface new leads.

### Generalizing beyond Vacademy / education

The original brief targeted online education companies in Qatar. The template at `templates/brief.md` is fully generic — drop in any vertical, any country. Examples that work without code changes:

- "Mid-size law firms in Mumbai for our practice-management SaaS"
- "D2C beauty brands in the US with $1–10M revenue for our 3PL service"
- "Series A-stage fintech startups in the UK for our compliance API"
- "Boutique hotels in Bali for our booking-engine integration"

If a vertical needs different enrichment (e.g. scrape Glassdoor for hiring signals, or LinkedIn for funding-stage info), add a new enricher under `src/enrich/`. The existing three are templates — `phones.py` is the simplest, `linkedin.py` shows the Serper-as-enricher pattern.

---

## Two paths for generating plan.json

### Path A — Anthropic API (recommended if you have a key)

The user adds `ANTHROPIC_API_KEY` to `.env`. Then:

```bash
python -m src plan <slug>
```

This calls Claude Opus 4.7 with adaptive thinking and returns a structured `SearchPlan` (Pydantic-validated). Cost: ~$0.05–0.20 per brief.

### Path B — Paste into any LLM (no API key required)

If the user has no API key, **you (the LLM reading this doc)** can act as stage 1 yourself:

1. Read `campaigns/<slug>/brief.md`.
2. Generate 25–40 Serper queries following the schema in `templates/plan.example.json` (or the existing `campaigns/qatar_online_edu/plan.json` as a worked example).
3. Save the JSON directly to `campaigns/<slug>/plan.json`.
4. Mark stage 1 done in `state.json` by appending to `stages.plan`:
   ```json
   "plan": { "done": true, "done_at": "<ISO timestamp>", "query_count": <N> }
   ```

Schema rules:
- `type` is `"search"` or `"maps"`.
- For `"maps"`, `location` is required (`"<City>, <Country>"`). For `"search"`, `location` is `null` and geography goes in the query string.
- Queries: 3–7 words, natural phrasing, no quotes, no `site:` operators, no boolean OR.
- Cover every in-scope subsegment in the brief.
- For each subsegment, generate both `search` queries (broad) and `maps` queries (one per city anchor).
- Aim for 25–40 total queries.

---

## File structure cheat sheet

```
v_marketing/
  AGENT.md                  # this file
  README.md                 # human-facing quickstart
  requirements.txt          # anthropic, requests, dotenv, pydantic
  .env.example              # SERPER_API_KEY (required), ANTHROPIC_API_KEY (optional)
  templates/
    brief.md                # template for new briefs
  src/
    __main__.py             # the CLI — every command routes through here
    campaign.py             # Campaign class, state helpers, dedupe keys
    plan.py                 # stage 1
    search.py               # stage 2 (skips already-executed queries)
    normalize.py            # stage 3 (merges with existing CSV)
    enrich/
      _fetch.py             # shared page-fetching helper
      phones.py             # stage 4a
      emails.py             # stage 4c
      linkedin.py           # stage 4b
  campaigns/
    <slug>/
      brief.md              # what you're targeting (human-written)
      plan.json             # concrete queries (LLM-written)
      state.json            # what's been done
      raw/                  # raw Serper output, one jsonl per search run
      leads.csv             # the leads
      leads.csv.bak         # auto-backup before every write
```

---

## What's in state.json (so you can read and update it)

```json
{
  "slug": "qatar_online_edu",
  "created_at": "2026-05-20T10:30:00Z",
  "last_activity_at": "2026-05-21T08:45:00Z",
  "stages": {
    "plan":            { "done": true, "done_at": "...", "query_count": 40 },
    "search":          { "runs": [{"at": "...", "queries_run": 40, "results": 479}],
                         "executed_queries": ["search|coding academy qatar online|", "..."] },
    "normalize":       { "runs": [{"at": "...", "total_leads": 283, "new_leads": 283}] },
    "enrich.phones":   { "runs": [{"at": "...", "phones_added": 22, "whatsapps_added": 18}] },
    "enrich.linkedin": { "runs": [{"at": "...", "found": 92}] },
    "enrich.emails":   { "runs": [{"at": "...", "found": 140}] }
  },
  "stats": {
    "total_leads": 283, "with_website": 247, "with_phone": 203,
    "with_whatsapp": 18, "with_email": 140, "with_linkedin": 92
  }
}
```

The `executed_queries` array uses the key format `"{type}|{query_lowercase}|{location_lowercase}"`. When you (LLM) append queries to `plan.json` manually, you do NOT need to update `executed_queries` — `search.py` computes them on the fly.

---

## Known limitations to flag if a user asks

1. **Serper Maps can return out-of-country results.** Filter in normalize if the user cares.
2. **LinkedIn hit rate is ~30%.** Many small institutes don't have LinkedIn company pages. Soften the search query (drop the quoted name) for higher recall + lower precision.
3. **Email scraping hit rate is ~50%.** Sites that gate contact info behind forms won't surface emails. Hunter.io / Apollo (paid) would lift this to ~70%.
4. **The CSV is a single file per campaign.** Don't open it in Excel while a stage is running — the writer will clobber unsaved edits. Open the `.bak` if you need to read while a job is going.

---

## Quick troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| "Campaign not found" | Slug typo or missing dir | `python -m src status` |
| "SERPER_API_KEY not set" | Missing `.env` | `cp .env.example .env`, edit |
| Stage 1 fails | No `ANTHROPIC_API_KEY` | Use Path B (LLM-written plan.json) |
| Search returns 0 results for some queries | Query too narrow or non-English | Edit `plan.json`, rephrase, re-run |
| Enricher hangs | Slow website timeouts | Already tightened to 6s; if still slow, lower `TIMEOUT` in `src/enrich/_fetch.py` |
| Want to start fresh | Sunk-cost the old campaign | `rm -rf campaigns/<slug>` (or rename it `<slug>_v1`) |
