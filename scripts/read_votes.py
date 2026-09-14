#!/usr/bin/env python3
"""Read back whatever the reader has voted on - in the main "Morning
Brief Feedback" tab (articles that were actually delivered) and, while
it exists, the "Candidates" tab (the full pool Claude chose from, so a
vote there can flag "this should have made the brief" even though it
never got sent) - for the recipe to fold into its article-selection
prompt as taste-calibration examples.

The Candidates tab is a temporary diagnostic (see
sheets_sync_candidates.py's own docstring for why) - this reads it if
it's there and simply skips it once it's gone, no separate flag needed.

Prints a JSON object to stdout: {"liked": [...], "disliked": [...]}, each a
list of {"source", "title"} objects, capped at MAX_PER_CATEGORY each. No
date filtering - votes lag behind delivery by a day or more (the reader
votes once they've actually read on the Kindle, or browsed candidates
later), so "recent" here means recently *voted*, not recently delivered.

A URL voted in both tabs is only counted once - the main tab wins ties,
since that's a vote on something actually read, not just a headline in
the candidate pool.

Usage:
    venv/bin/python read_votes.py

Required environment:
    GOOGLE_APPLICATION_CREDENTIALS - path to the service account JSON key
    SHEET_ID                       - the target sheet's id (from its URL)

Prints {"liked": [], "disliked": []} (not an error) if the sheet can't be
reached - a missing feedback signal should never be why the whole build
fails.
"""

import json
import os
import sys

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
MAX_PER_CATEGORY = 25


def collect_votes(records, seen_urls):
    """{url: {"vote": "up"|"down", "source":, "title":}} for rows with a
    real vote and a URL not already claimed by an earlier (higher
    priority) sheet.
    """
    votes = {}
    for row in records:
        vote = str(row.get("Vote", "")).strip().lower()
        url = str(row.get("URL", "")).strip()
        if vote not in ("up", "down") or not url or url in seen_urls:
            continue
        votes[url] = {"vote": vote, "source": row.get("Source", ""), "title": row.get("Title", "")}
        seen_urls.add(url)
    return votes


def main():
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    empty = {"liked": [], "disliked": []}

    if not creds_path or not sheet_id:
        print(json.dumps(empty))
        return

    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(sheet_id)
    except Exception as err:
        print("Could not open the feedback sheet: %s" % err, file=sys.stderr)
        print(json.dumps(empty))
        return

    seen_urls = set()
    all_votes = {}

    try:
        all_votes.update(collect_votes(spreadsheet.sheet1.get_all_records(), seen_urls))
    except Exception as err:
        print("Could not read the main feedback tab: %s" % err, file=sys.stderr)

    try:
        candidates_ws = spreadsheet.worksheet("Candidates")
        all_votes.update(collect_votes(candidates_ws.get_all_records(), seen_urls))
    except gspread.WorksheetNotFound:
        pass  # dropped once brief quality is good enough - expected eventually
    except Exception as err:
        print("Could not read the Candidates tab: %s" % err, file=sys.stderr)

    liked, disliked = [], []
    for entry in all_votes.values():
        target = liked if entry["vote"] == "up" else disliked
        target.append({"source": entry["source"], "title": entry["title"]})

    print(json.dumps({
        "liked": liked[-MAX_PER_CATEGORY:],
        "disliked": disliked[-MAX_PER_CATEGORY:],
    }))


if __name__ == "__main__":
    main()
