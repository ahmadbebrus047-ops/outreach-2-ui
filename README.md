# Medical Billing Outreach

Two-part pipeline: (1) collect healthcare-provider prospects from the public
NPPES NPI Registry into a deduplicated flat file; (2) send a throttled daily
email campaign with automatic 7-day reminders, opt-out suppression, and
per-recipient send tracking.

## Data sources
1. **NPPES NPI Registry** (primary, free, keyless) — name, practice + mailing
   address, phone, fax, specialty/taxonomy, credential, entity type.
2. **CMS `data.cms.gov` Medicare enrollment** (second source, free, keyless) —
   joined by NPI to add `medicare_enrolled` and CMS `provider_type_desc`. A
   Medicare-enrolled clinic is a stronger medical-billing prospect. Toggle with
   `CMS_ENRICH_ENABLED=0` to skip.

Neither government source publishes email addresses — that's by design, not a
gap. See enrichment below.

## Emails

The project supports a **no-API public-web enricher**. Set `ENRICHER=web` and
run `python -m jobs.enrich_emails`. It searches public search-result pages,
then visits public practice/business pages and their likely Contact/About/Team
pages to extract email addresses that are actually published on the web. It
does not guess addresses and never overwrites an existing email.

The scraper uses a small pluggable search-engine layer (DuckDuckGo HTML, Brave
Search HTML, then Bing HTML as fallback). Search-engine HTML can change, so the
parsers are isolated in `core/scraper.py`. The crawler respects `robots.txt`,
uses bounded timeouts, and does not attempt CAPTCHA or anti-bot bypasses.

Each successful result records `email_source` and `email_confidence` in
`prospects.csv`. `found` means the heuristic confidence is high;
`unverified` means an email was found but the evidence is weaker.

Useful settings:
```bash
export ENRICHER=web
export SEARCH_PAUSE_SECONDS=1.5
export PAGE_PAUSE_SECONDS=0.75
export SCRAPER_TIMEOUT_SECONDS=15
export SEARCH_RESULTS_PER_QUERY=8
export MAX_SITES_PER_PROSPECT=5
```

The existing optional `apollo` and `hunter` enrichers remain available if you
are permitted to use those providers.

## Web GUI (steps 1 & 2)

A browser console drives the two data-building steps without the command line.

```bash
pip install -r requirements.txt
export APOLLO_API_KEY="..."        # needed for step 2
python -m webapp.server            # open http://127.0.0.1:5000
```

**Step 1 — Fetch prospects.** All 50 states + DC + US territories are listed
with a live done / remaining tracker and per-state row counts. Select any set of
states and fetch them (each runs in the background; the tracker polls). A
taxonomy box maps to `NPPES_TAXONOMY` — leave it blank for all providers, or
pick a description like `Family Medicine` (the box suggests common values).

**Step 2 — Find emails (Apollo).** The prospect CSV is shown as a selectable
table (search + filter by state/status). Select the rows you want emails for and
run enrichment; the backend calls Apollo in bulk (10 people/request) and writes
results back to `prospects.csv`. Three result tables are shown:

| Table | Meaning |
|-------|---------|
| Emails fetched | Apollo returned an email (`found` / `unverified`) |
| No email available | Apollo ran but had no email (`not_found`) — not retried automatically |
| Not fetched | skipped or errored this run — safe to re-select and retry |

Existing emails are never overwritten, and already-fetched rows are not
re-billed. A found email costs ~1 Apollo credit; a no-match costs 0.

### Apollo API notes (2026)
- Auth is the **`x-api-key` header** (Apollo removed the old body `api_key`).
- Endpoints: `POST /api/v1/people/match` and `POST /api/v1/people/bulk_match`.
- **Plan/credits:** the Basic plan (~$49/mo, ~1,000 credits) has *limited* API
  access; reliable programmatic/automated enrichment realistically needs the
  **Professional plan** ($79/mo, higher/fair-use credits) or Organization for
  full ("advanced") API access. Credits **do not roll over**. If ~6,000
  emails/month is the real target, Professional is the sensible tier — Basic's
  ~1,000 credits/mo won't cover it, and the standalone Basic API is throttled.
  Verify the current tier limits in Apollo's billing page before purchase.

## Layout
```
core/       config, models, repositories, NPPES + CMS clients, Apollo enricher,
            per-state status tracker, mailer, campaign logic
jobs/       runnable entrypoints (fetch, enrich, send, suppress)
webapp/     Flask backend (server.py) + single-file UI (static/index.html)
data/       prospects.csv, sent_log.csv, suppression.csv, state_status.json
logs/       rotating logs per module
```

## Setup
```bash
pip install -r requirements.txt
```
Google app for sending:
1. Google Cloud Console → new project → enable **Gmail API**.
2. Create OAuth **Desktop** credentials → download as `credentials.json` in root.
3. First real send opens a browser once to authorize; `token.json` is cached.

Set env vars (or edit `core/config.py`):
```bash
export SENDER_EMAIL="you@yourdomain.com"
export SENDER_NAME="Your Company"
export TARGET_STATES="TX,CA,NY,FL"
export DAILY_SEND_LIMIT=10
export PHYSICAL_ADDRESS="123 Example St, Dallas, TX 75201"
```

## Run
```bash
python -m jobs.fetch_prospects         # collect + dedup into data/prospects.csv
python -m jobs.enrich_emails           # add business emails via licensed vendor
python -m jobs.send_campaign --dry-run # preview today's batch, no send
python -m jobs.send_campaign           # real send (initial + due reminders)
python -m jobs.suppress foo@bar.com    # honor an opt-out
```

## Cron
```cron
# Fetch new prospects every day at 02:00
0 2 * * *  cd /path/to/outreach && /usr/bin/python3 -m jobs.fetch_prospects

# Enrich newly-added prospects with emails at 03:00
0 3 * * *  cd /path/to/outreach && /usr/bin/python3 -m jobs.enrich_emails

# Send the daily batch at 09:00 (includes any due 7-day reminders)
0 9 * * *  cd /path/to/outreach && /usr/bin/python3 -m jobs.send_campaign
```
Reminders don't need their own cron: the daily send job checks the sent-log and
automatically queues anyone whose last contact was ≥ `REMINDER_AFTER_DAYS` ago
(capped at `MAX_REMINDERS`), prioritizing them before new sends within the same
daily limit.

## Compliance notes (please read)
- Every email carries your physical address and opt-out instructions
  (`core/templates.py`). Keep them.
- Process replies containing "UNSUBSCRIBE" the same day via `jobs.suppress`.
- Ten sends/day from a new domain is deliverability-friendly; ramp slowly.
- Fill emails only from sources you're permitted to use. Cold-emailing addresses
  harvested off websites is an aggravating factor under CAN-SPAM and a fast route
  to a blocklisted domain — this tool is built to keep you on the right side of it.
```
