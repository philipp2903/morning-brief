#!/usr/bin/env python3
"""Read back whatever the reader has voted on in the "Morning Brief
Feedback" Google Sheet, for the recipe to fold into its article-selection
prompt as taste-calibration examples.

Prints a JSON object to stdout: {"liked": [...], "disliked": [...]}, each a
list of {"source", "title"} objects, most-recently-voted first, capped at
MAX_PER_CATEGORY each. No date filtering - votes lag behind delivery by a
day or more (the reader votes once they've actually read on the Kindle),
so "recent" here means recently *voted*, not recently delivered.

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
        ws = gc.open_by_key(sheet_id).sheet1
        records = ws.get_all_records()
    except Exception as err:
        print("Could not read the feedback sheet: %s" % err, file=sys.stderr)
        print(json.dumps(empty))
        return

    liked, disliked = [], []
    for row in records:
        vote = str(row.get("Vote", "")).strip().lower()
        entry = {"source": row.get("Source", ""), "title": row.get("Title", "")}
        if vote == "up":
            liked.append(entry)
        elif vote == "down":
            disliked.append(entry)

    # Rows are in sheet order (oldest delivered first) - most recently
    # voted isn't quite knowable without a vote timestamp, but most
    # recently *delivered* is the next best thing and is free from the
    # row order already there.
    print(json.dumps({
        "liked": liked[-MAX_PER_CATEGORY:],
        "disliked": disliked[-MAX_PER_CATEGORY:],
    }))


if __name__ == "__main__":
    main()
