#!/usr/bin/env python3
"""Decide whether a *scheduled* run of the workflow should actually build.

GitHub's cron is UTC-only, but the brief should be created at 04:00 Berlin
time all year, and Berlin is UTC+2 in summer (CEST) and UTC+1 in winter
(CET). A single fixed UTC cron can only be right for half the year, so the
workflow fires at BOTH 02:00 and 03:00 UTC and this gate lets the right one
through:

    summer  02:00 UTC = 04:00 Berlin -> proceeds; 03:00 UTC = 05:00 -> skipped
    winter  02:00 UTC = 03:00 Berlin -> skipped;  03:00 UTC = 04:00 -> proceeds

Rules for a scheduled run (manual runs always proceed):
  1. Berlin hour must be 4-8. Earlier is the wrong-season duplicate (see
     above); later means GitHub delayed it so badly the news is stale.
  2. Skip if today's edition was already delivered - detected from the
     "chore: articles delivered ..." commit the workflow itself pushes after
     every real send. This is what stops the second cron from sending a
     duplicate in summer - and what lets it act as an automatic retry if
     the first one failed or never fired.

Hour-based on its own would be simpler, but GitHub regularly delays
scheduled runs by 5-10 minutes (observed here: 03:06-03:10 for a 03:00
cron) and occasionally much more; with only "hour == 4" a delay past 05:00
would silently skip the day.

Usage (in CI): needs EVENT_NAME, GITHUB_REPOSITORY, GH_TOKEN and
GITHUB_OUTPUT; writes proceed=true|false.
"""

import datetime
import json
import os
import sys
import urllib.request
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
EARLIEST_HOUR = 4   # inclusive
LATEST_HOUR = 8     # inclusive
DELIVERED_PREFIX = "chore: articles delivered"


def berlin_midnight_utc(now_utc):
    now = now_utc.astimezone(BERLIN)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(datetime.timezone.utc)


def decide(now_utc, delivered_today):
    """(proceed, reason) for a scheduled run at now_utc (aware datetime)."""
    hour = now_utc.astimezone(BERLIN).hour
    if hour < EARLIEST_HOUR:
        return False, "Berlin hour is %02d - too early (the other cron's slot for this season)" % hour
    if hour > LATEST_HOUR:
        return False, "Berlin hour is %02d - too late, the news would be stale" % hour
    if delivered_today:
        return False, "today's edition was already delivered"
    return True, "Berlin hour is %02d and nothing delivered yet today" % hour


def count_delivered_today(now_utc, repo, token):
    since = berlin_midnight_utc(now_utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    request = urllib.request.Request(
        "https://api.github.com/repos/%s/commits?since=%s&per_page=50" % (repo, since),
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        commits = json.load(response)
    return sum(1 for c in commits if c["commit"]["message"].startswith(DELIVERED_PREFIX))


def main():
    out = os.environ.get("GITHUB_OUTPUT")

    def finish(proceed, reason):
        print("proceed=%s - %s" % (str(proceed).lower(), reason))
        if out:
            with open(out, "a") as handle:
                handle.write("proceed=%s\n" % str(proceed).lower())
        sys.exit(0)

    if os.environ.get("EVENT_NAME") != "schedule":
        finish(True, "not a scheduled run (%s)" % os.environ.get("EVENT_NAME"))

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    try:
        delivered = count_delivered_today(
            now_utc, os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
        ) > 0
    except Exception as err:
        # If the lookup fails, fall back to the hour rule alone: a possible
        # duplicate send beats silently skipping the whole day.
        print("Could not check for an earlier delivery today (%s); using the hour rule only." % err)
        delivered = False
    proceed, reason = decide(now_utc, delivered)
    finish(proceed, reason)


if __name__ == "__main__":
    main()
