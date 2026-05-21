# v_marketing — B2B lead-research pipeline

A reusable tool to turn a plain-English brief into an enriched CSV of leads. Originally built for Vacademy, but the pipeline is generic: any B2B vertical, any geography.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add SERPER_API_KEY (required) and ANTHROPIC_API_KEY (optional)
python -m src         # interactive menu
```

## The pipeline

```
brief.md  →  plan.json  →  raw/*.jsonl  →  leads.csv  →  leads.csv (enriched)
(stage 0)    (stage 1)      (stage 2)      (stage 3)     (stage 4)
write it     Claude         Serper         normalize     scrape + Serper
                            /search+/maps  + dedupe      for phone/email/linkedin
```

Each stage is independent, idempotent, and records what it did in `state.json`. Re-running a stage skips already-completed work.

## Directory layout

```
campaigns/
  <slug>/
    brief.md            # what you're targeting (you write this)
    plan.json           # concrete Serper queries (stage 1 writes)
    state.json          # what's been done (every stage updates)
    raw/<ts>.jsonl      # raw Serper output (stage 2 writes)
    leads.csv           # the actual leads (stages 3 + 4 write)
```

## Commands

| Command | What it does |
|---|---|
| `python -m src` | Interactive menu — shows campaigns, asks what to do |
| `python -m src status` | One-line summary of every campaign |
| `python -m src new <slug>` | Create a new campaign (drops a brief template) |
| `python -m src plan <slug>` | Stage 1 — needs `ANTHROPIC_API_KEY` |
| `python -m src search <slug>` | Stage 2 — Serper. Skips already-executed queries. |
| `python -m src normalize <slug>` | Stage 3 — flatten raw → CSV. Merges with existing CSV. |
| `python -m src enrich <slug>` | Stage 4 — phones, emails, LinkedIn (in that order) |
| `python -m src enrich <slug> --only emails` | Just one enricher |
| `python -m src continue <slug>` | Run whatever stage has new work pending |
| `python -m src run-all <slug>` | Full pipeline end-to-end |

## How resumability works

- **New queries** — edit `plan.json`, add queries, re-run `search`. It skips ones already in `state.search.executed_queries`. Then re-run `normalize` to fold the new results into `leads.csv`.
- **Re-enrich** — re-run any enricher; it only touches rows where the target column is empty. Already-enriched rows are untouched.
- **No Anthropic key** — see [AGENT.md](AGENT.md) for the "paste your brief into an LLM" alternative path. Every other stage works fine with just `SERPER_API_KEY`.

## For other developers picking this up

Read [AGENT.md](AGENT.md). It's written for an LLM but reads fine for humans too — covers the interview script for new briefs, decision trees for common tasks, and the two paths (Anthropic SDK vs manual LLM hand-off).

## Costs (rough)

- 40-query plan, 50-200 leads: **~$0.05** Serper.
- LinkedIn enrichment: **1 Serper credit per lead**. 300 leads ≈ $0.30.
- Phones and emails enrichment: **free** (scrape only).
- Anthropic API for plan: **~$0.10 per brief** (with caching, cheaper on repeats).
