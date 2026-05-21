# Brief: Qatar online education companies

**Slug:** `qatar_online_edu`
**Created:** 2026-05-20
**Volume target (first run):** 50 leads
**Re-run cadence:** one-shot for v1; weekly dedupe later

## Product we're selling

Vacademy — modular SaaS for education institutes: admission CRM, LMS, live sessions, assessments, marketing, AI tools. Customers pick what they use.

## Who we want to find

Small-to-mid **online education companies** operating in Qatar — companies that *teach* online (or hybrid), have a website, and would benefit from an end-to-end software platform.

### In scope — pick all four subsegments

1. **STEM / coding academies** — coding, robotics, AI, math for kids and teens. *(Reference: Edostream, our existing Qatar customer.)*
2. **Online tutoring services** — IB, IGCSE, A-level, SAT, university entrance prep, academic support.
3. **Language training** — IELTS, TOEFL, English, Arabic, French. Qatar is ~85% expat so demand is heavy.
4. **Professional certification training** — PMP, CFA, ACCA, PRINCE2, ITIL, cybersecurity, data science bootcamps. Targets Qatar's finance + oil/gas workforce.
5. Startup Edtech Companies

### Out of scope (disqualifiers — drop these in the filter)

- **K-12 schools** (we don't sell to schools right now)
- **Universities and university colleges**
- **Government training centers** and ministry-run programs
- **Big chains** with their own tech teams — explicit blocklist examples: Byju's, Aakash, Unacademy, PhysicsWallah, Vedantu, Khan Academy (any presence in Qatar). General rule: > ~50 employees or > ~5 branches → out.
- **Individual home tutors** with no business entity, no website, just a personal profile.
- Pure content sellers (Udemy-style course marketplaces) with no live teaching.

## Geography

**Country:** Qatar.
**City anchors for Maps queries:** Doha, Al Rayyan, Lusail, Al Wakrah, Al Khor. (Most leads will be Doha-metro regardless.)

## What a great lead looks like

- Has a website with course/program listings
- Lists a phone number or whatsapp number and/or contact form
- Mentions live classes, cohorts, instructors, or schedule — not just self-paced video
- Small founding team, visible on LinkedIn or About page
- Already operating online or hybrid

## What junk looks like

- Affiliate landing pages with no real institute behind them
- YouTube channels / Instagram pages with no website
- Generic directory listings (Justdial-style) with no actual business
- Course aggregators / marketplaces
- Companies whose primary business is something else (a school that happens to offer one online course)

## Output columns we want in leads.csv

Required: `name, website, segment, city, country, phone, email, linkedin_url, source_query, raw_source, confidence_score, notes`
Reserved for stage 5 (messaging): `status, last_contacted_at, channel, message_id`
