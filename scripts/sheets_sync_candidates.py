#!/usr/bin/env python3
"""Append today's *full* candidate pool - everything Claude had to choose
from, not just what got selected - to a "Candidates" tab in the feedback
spreadsheet, so the reader can eyeball what got passed over and upvote
anything that should have made the brief.

This is explicitly a temporary diagnostic tool (see morning_brief.recipe's
own comments on ALL_CANDIDATES_FILE): the plan is to run it for a few days
while judging selection quality, then drop it - at which point this
script, its workflow step, and the "Candidates" tab all get deleted, and
only the main delivered-articles tab remains. Kept as a separate script
(rather than folded into sheets_sync.py) specifically so removing it later
is a clean, single-file deletion.

Usage:
    venv/bin/python sheets_sync_candidates.py <path-to-all_candidates.json>

Where that JSON file is a list of {"date", "source", "title", "url",
"age_hours", "selected"} objects - written by the recipe itself (see
parse_feeds() in morning_brief.recipe) right after selection, so this
always reflects a real build's actual candidate pool.

Required environment:
    GOOGLE_APPLICATION_CREDENTIALS - path to the service account JSON key
    SHEET_ID                       - the target sheet's id (from its URL)
"""

import json
import os
import sys

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
WORKSHEET_TITLE = "Candidates"
HEADER = ["Date", "Source", "Title", "URL", "Age (h)", "Selected", "Vote"]


def get_or_create_worksheet(spreadsheet):
    try:
        return spreadsheet.worksheet(WORKSHEET_TITLE)
    except gspread.WorksheetNotFound:
        pass

    # No local credentials exist to set this tab up by hand (deleted after
    # the main "Morning Brief Feedback" tab was set up - see that setup
    # for why), so this provisions itself the first time it actually runs
    # in CI, where the credentials do live (as a GitHub secret).
    ws = spreadsheet.add_worksheet(title=WORKSHEET_TITLE, rows=2000, cols=len(HEADER))
    ws.update([HEADER], "A1")
    body = {
        "requests": [
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "endRowIndex": 5000,
                        "startColumnIndex": 6,
                        "endColumnIndex": 7,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [{"userEnteredValue": "up"}, {"userEnteredValue": "down"}],
                        },
                        "showCustomUi": True,
                        "strict": False,
                    },
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount",
                }
            },
        ]
    }
    spreadsheet.batch_update(body)
    return ws


def main():
    if len(sys.argv) != 2:
        print("usage: sheets_sync_candidates.py <all_candidates.json>", file=sys.stderr)
        sys.exit(2)

    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        candidates = json.load(handle)

    if not candidates:
        print("No candidates to sync today.")
        return

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    if not creds_path or not sheet_id:
        print("GOOGLE_APPLICATION_CREDENTIALS and SHEET_ID must both be set.", file=sys.stderr)
        sys.exit(1)

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(sheet_id)
    ws = get_or_create_worksheet(spreadsheet)

    rows = [
        [
            c.get("date", ""),
            c.get("source", ""),
            c.get("title", ""),
            c.get("url", ""),
            c.get("age_hours", ""),
            "yes" if c.get("selected") else "no",
            "",
        ]
        for c in candidates
    ]
    ws.append_rows(rows, value_input_option="RAW")
    print("Synced %d candidate(s) to the Candidates sheet." % len(rows))


if __name__ == "__main__":
    main()
