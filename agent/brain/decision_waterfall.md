---
name: Decision Waterfall
version: 4.0
last_updated: 2026-07-03
---

# Decision Waterfall (v4.0 — Business Agent)

Priority order for deciding what to do each cycle.
Each gate is evaluated top-to-bottom. First match wins.

## Priority 1: No Opportunities? Scan

IF opportunities.md has 0 open opportunities
THEN action: 'scan_gigs'

- Can't earn money without a pipeline
- Always keep opportunities flowing
- Generate 3+ per scan

## Priority 2: Opportunities But No Leads? Score Them

IF opportunities exist AND leads.md has 0 scored leads
THEN action: 'track_leads'

- Score each opportunity 1-10
- Suggest follow-up action for each
- Move high-score leads to active pursuit

## Priority 3: No Content This Week? Create

IF content-log.md has 0 entries in last 7 days
THEN action: 'create_content'

- Content drives inbound leads
- 2 posts per week minimum
- Technical, specific, demonstrates expertise

## Priority 4: Haven't Built Reputation Today? Engage

IF no reputation-building action in last 24 hours
THEN action: 'build_reputation'

- Reddit comments in r/LocalLLaMA, r/MachineLearning
- Answer questions, demonstrate expertise
- Don't spam — be genuinely helpful

## Priority 5: Stale Opportunities? Re-scan

IF last opportunity scan was >3 days ago
THEN action: 'scan_gigs'

- Opportunities go stale fast
- Keep pipeline fresh

## Priority 6: Reflect and Optimize

IF all above are satisfied
THEN action: 'reflect'

- Review what's working
- Adjust strategy
- Identify new niches or platforms

## Default Fallback

IF no conditions met
THEN action: 'scan_gigs'
