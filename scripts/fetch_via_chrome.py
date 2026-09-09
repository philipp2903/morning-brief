#!/usr/bin/env python3
"""Fetch a URL through a real, persistently-running Chrome instance on
this machine, via Chrome DevTools Protocol - not a fresh automation
profile.

Why this exists: NYT and FT both run bot-detection (DataDome and
Cloudflare respectively) that blocks Calibre's own QtWebEngine fetcher,
and also blocks a *freshly launched* Playwright/Selenium browser (which
sets automation flags like navigator.webdriver by default) - confirmed
by testing both directly. Attaching to an already-running, normally
launched Chrome via connect_over_cdp does not set those flags and gets
through to the real page (paywall or article, not a bot-block page) -
also confirmed by testing.

The Chrome instance itself is managed separately (see
com.morningbrief.chrome.plist) - this script only attaches to it. You
need to have logged into nytimes.com / ft.com once in that specific
Chrome profile (not your everyday one) for paywalled content to work;
see the setup instructions in the repo README.

Usage:
    venv/bin/python fetch_via_chrome.py <url>

Prints the fully-rendered page HTML to stdout. Exits non-zero (with a
reason on stderr) if it can't reach the Chrome instance or the fetch
fails outright.
"""

import os
import sys

from playwright.sync_api import sync_playwright

CDP_URL = os.environ.get("MORNING_BRIEF_CDP_URL", "http://localhost:9333")

# Sites known to need this path. Anything else should go through
# Calibre's normal fetcher instead - this is slower and depends on a
# machine-local Chrome instance being up.
COOKIE_CONSENT_SELECTORS = [
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('I accept')",
]


def dismiss_cookie_banner(page):
    for selector in COOKIE_CONSENT_SELECTORS:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=2000):
                button.click(timeout=2000)
                return
        except Exception:
            continue


def main():
    if len(sys.argv) != 2:
        print("usage: fetch_via_chrome.py <url>", file=sys.stderr)
        sys.exit(2)
    url = sys.argv[1]

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
            except Exception:
                pass  # partial load is still usually a real page by this point
            dismiss_cookie_banner(page)
            html = page.content()
            page.close()
    except Exception as err:
        print(f"Could not fetch {url} via Chrome CDP at {CDP_URL}: {err}", file=sys.stderr)
        sys.exit(1)

    sys.stdout.write(html)


if __name__ == "__main__":
    main()
