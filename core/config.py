"""
Central configuration. All tunables live here so the rest of the code
stays declarative. Override any value via environment variables.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

# The single flat file that holds all prospects (append-only, deduplicated).
PROSPECTS_FILE = DATA_DIR / "prospects.csv"
# Tracks who we've emailed and when, so we never double-send.
SENT_LOG_FILE = DATA_DIR / "sent_log.csv"
# Opt-out / bounce suppression. Anyone here is never contacted again.
SUPPRESSION_FILE = DATA_DIR / "suppression.csv"

for _d in (DATA_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Data source: NPPES NPI Registry (public US gov API) ---------------------
# https://npiregistry.cms.gov/api-page  --  no key required.
NPPES_API_URL = "https://npiregistry.cms.hhs.gov/api/"
NPPES_API_VERSION = "2.1"
# States to pull. Trim or extend as you like.
TARGET_STATES = os.getenv("TARGET_STATES", "TX,CA,NY,FL").split(",")
# Taxonomy keyword to bias toward independent clinics / physician practices.
NPPES_TAXONOMY = os.getenv("NPPES_TAXONOMY", "")  # e.g. "Family Medicine"
NPPES_PAGE_SIZE = 200          # API max per request
NPPES_MAX_PER_STATE = int(os.getenv("NPPES_MAX_PER_STATE", "1000"))
NPPES_REQUEST_PAUSE = 0.5      # seconds between requests, be a good citizen

# --- Second source: CMS Medicare enrollment (data.cms.gov) -------------------
# When on, each state's prospects are annotated with Medicare enrollment status
# and CMS provider-type description (joined by NPI). Purely additive.
CMS_ENRICH_ENABLED = os.getenv("CMS_ENRICH_ENABLED", "1") == "1"

# --- Email sending -----------------------------------------------------------
# Gmail API app credentials (the "app on Google" you create).
GOOGLE_CREDENTIALS_FILE = BASE_DIR / "credentials.json"
GOOGLE_TOKEN_FILE = BASE_DIR / "token.json"

SENDER_EMAIL = os.getenv("SENDER_EMAIL", "you@yourdomain.com")
SENDER_NAME = os.getenv("SENDER_NAME", "Your Company")

DAILY_SEND_LIMIT = int(os.getenv("DAILY_SEND_LIMIT", "10"))
REMINDER_AFTER_DAYS = int(os.getenv("REMINDER_AFTER_DAYS", "7"))
MAX_REMINDERS = int(os.getenv("MAX_REMINDERS", "2"))  # stop nagging eventually
SEND_PAUSE_SECONDS = 8         # gap between individual sends

# CAN-SPAM requires a real physical postal address in every commercial email.
PHYSICAL_ADDRESS = os.getenv(
    "PHYSICAL_ADDRESS", "123 Example St, Suite 100, Dallas, TX 75201"
)
# Where opt-out replies should be directed (a mailbox you monitor).
UNSUBSCRIBE_CONTACT = os.getenv("UNSUBSCRIBE_CONTACT", "unsubscribe@yourdomain.com")

# --- All US states + DC + territories (valid values for state fetch) ---------
# NPPES accepts standard USPS two-letter codes. This is the full set the UI
# lets you fetch one-by-one.
ALL_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",  # District of Columbia
    # US territories NPPES also indexes:
    "PR", "VI", "GU", "AS", "MP",
]

# Human-readable names for the UI.
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia", "PR": "Puerto Rico",
    "VI": "U.S. Virgin Islands", "GU": "Guam", "AS": "American Samoa",
    "MP": "Northern Mariana Islands",
}

# The prospect categories this project targets. `query` is the NPPES
# taxonomy_description search; `codes` keeps only rows holding one of these
# NUCC taxonomy codes (a trailing * is a prefix match). Family NP has no exact
# NPPES description, so it searches all NPs and filters by code.
PROSPECT_CATEGORIES = {
    "Multi-Specialty Group": {"query": "Multi-Specialty", "codes": ["261QM1300X", "193200000X"]},
    "Registered Dietitian": {"query": "Dietitian, Registered", "codes": ["133V*"]},
    "Family Nurse Practitioner": {"query": "Nurse Practitioner", "codes": ["363LF0000X"]},
    "Family Medicine": {"query": "Family Medicine", "codes": ["207Q*"]},
}

# Tracks which states have been fetched, how many rows, and when.
STATE_STATUS_FILE = DATA_DIR / "state_status.json"

# --- Apollo email enrichment (paid API) --------------------------------------
# Apollo authenticates with an `x-api-key` HEADER (NOT a body field).
# Programmatic/automated API use realistically needs the Professional plan or
# higher; the Basic tier's API access is limited. See notes in the README.
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "HCPV0rWbITRWhC5PO2BsVQ")
APOLLO_MATCH_URL = "https://api.apollo.io/api/v1/people/match"
APOLLO_BULK_MATCH_URL = "https://api.apollo.io/api/v1/people/bulk_match"
# People Search (no credits) resolves name + location to an Apollo person id,
# which bulk_match can then enrich. Needs a key scoped to this endpoint.
APOLLO_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"
APOLLO_SEARCH_ENABLED = os.getenv("APOLLO_SEARCH_ENABLED", "1") == "1"
# Apollo caps bulk_match at 10 people per request.
APOLLO_BULK_SIZE = 10
# Whether to also try to reveal personal emails (costs the same 1 credit if
# found, but personal emails are riskier for cold outreach - default off).
APOLLO_REVEAL_PERSONAL = os.getenv("APOLLO_REVEAL_PERSONAL", "0") == "1"
# Look up each prospect's practice domain (core/website_finder.py) before
# Apollo. Off by default: free search-engine HTML blocks automated queries.
WEBSITE_LOOKUP = os.getenv("WEBSITE_LOOKUP", "0") == "1"
# Pause between bulk requests to respect per-minute rate limits.
APOLLO_REQUEST_PAUSE = float(os.getenv("APOLLO_REQUEST_PAUSE", "1.0"))
