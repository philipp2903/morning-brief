#!/usr/bin/env python3
"""Append today's delivered articles to the "Morning Brief Feedback" Google
Sheet, one row per article, with the Vote column left blank.

The reader votes later, on their own time, from the Sheets app on their
phone (a Kindle Paperwhite has no browser or mail client, so voting can't
happen inline in the periodical itself - this is the out-of-band mechanism
for that). read_votes.py is the other half: it reads back whatever's been
voted on since, for the next build's article selection.

Usage:
    venv/bin/python sheets_sync.py <path-to-today_articles.json>

Where that JSON file is a list of {"date", "source", "title", "url"}
objects - written by the recipe itself (see save_history() in
morning_brief.recipe) after a real send, so only what was actually
delivered ends up in the sheet.

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


def main():
    if len(sys.argv) != 2:
        print("usage: sheets_sync.py <today_articles.json>", file=sys.stderr)
        sys.exit(2)

    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        articles = json.load(handle)

    if not articles:
        print("No articles to sync today.")
        return

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    if not creds_path or not sheet_id:
        print("GOOGLE_APPLICATION_CREDENTIALS and SHEET_ID must both be set.", file=sys.stderr)
        sys.exit(1)

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(sheet_id).sheet1

    rows = [
        [a.get("date", ""), a.get("source", ""), a.get("title", ""), a.get("url", ""), ""]
        for a in articles
    ]
    ws.append_rows(rows, value_input_option="RAW")
    print("Synced %d article(s) to the feedback sheet." % len(rows))


if __name__ == "__main__":
    main()
