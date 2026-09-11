#!/usr/bin/env python3
"""Fetch a URL through a real, persistently-running Chrome instance on
this machine (via CDP, not a fresh automation profile - see below), then
extract clean article content with Mozilla's Readability.js - the same
library behind Firefox's Reader View - injected into that live page.

Why a real Chrome, not Calibre's own fetcher: NYT and The Economist both
run bot-detection (DataDome and Cloudflare respectively) that blocks
Calibre's QtWebEngine fetcher, and also blocks a *freshly launched*
Playwright/Selenium browser (which sets automation flags like
navigator.webdriver by default) - confirmed by testing both directly.
Attaching to an already-running, normally launched Chrome via
connect_over_cdp does not set those flags and gets through to the real
page. The Chrome instance itself is managed separately (see
com.morningbrief.chrome.plist); you need to be logged into nytimes.com /
economist.com once in that specific profile for paywalled content.

Why Readability.js instead of Calibre's auto_cleanup: on a real build,
auto_cleanup's older readability port either threw outright on several
modern JS-framework pages (silently falling back to the *raw* page - full
cookie-vendor lists, sitemaps, nav trees) or otherwise failed to separate
article body from site chrome. Readability.js is actively maintained
against exactly this class of modern site and is what Reader View / most
browser reading-mode features are built on.

Usage:
    venv/bin/python fetch_via_chrome.py <url>

Prints extracted article HTML (title + content) to stdout on success.
Falls back to the full rendered page if Readability can't parse it (rare,
but better than emitting nothing). Exits non-zero (with a reason on
stderr) only if the fetch itself fails outright.
"""

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP_URL = os.environ.get("MORNING_BRIEF_CDP_URL", "http://localhost:9333")
READABILITY_JS = Path(__file__).parent / "vendor" / "Readability.js"

COOKIE_CONSENT_SELECTORS = [
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('I accept')",
]

EXTRACT_SCRIPT = """
() => {
    const clone = document.cloneNode(true);
    const article = new Readability(clone).parse();
    if (!article || !article.content) return null;
    return {title: article.title || '', content: article.content};
}
"""

# The Athletic (and other Next.js-built sites) render every <img> with a
# real photo URL in data-src but a 1x1 transparent placeholder already
# sitting in src - the swap only happens client-side, via an
# IntersectionObserver, once the image actually scrolls into view.
# Confirmed directly on a raw fetch of a live Athletic article: every <img>
# had src="data:image/gif;base64,..." and the real CDN URL in data-src. A
# page that's only ever goto()'d and never scrolled never fires that
# observer, so Readability's document.cloneNode(true) snapshot captures the
# placeholder - which then fails the recipe's own
# MIN_IMAGE_DIMENSION check and gets dropped, i.e. exactly the "no
# pictures" symptom. Scrolling through the full page before extracting
# mimics what a human reader does and lets each site's own lazy-load JS do
# the swap for us, which is more reliable than trying to special-case every
# site's data-src/data-original/etc. attribute naming after the fact.
SCROLL_SCRIPT = """
async () => {
    const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const step = Math.max(400, Math.floor(window.innerHeight * 0.8));
    for (let i = 0; i < 40; i++) {
        window.scrollBy(0, step);
        await delay(150);
        const atBottom = window.scrollY + window.innerHeight >= document.body.scrollHeight - 2;
        if (atBottom) break;
    }
    window.scrollTo(0, 0);
    await delay(300);
}
"""


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
            if not browser.contexts:
                # browser.new_context() is the obvious fallback here, but it
                # doesn't work on a real, normally-launched Chrome profile
                # (only on a browser Playwright itself launched) - confirmed
                # directly: it fails with "Protocol error
                # (Browser.setDownloadBehavior): Browser context management
                # is not supported", which took down every single article in
                # one build. An empty browser.contexts means the persistent
                # Chrome window has no open tabs at all right now (e.g. it
                # got relaunched since the last successful run) - that's
                # what actually needs fixing, not a code workaround here.
                raise RuntimeError(
                    "Chrome at %s has no open browser context (no tabs open). "
                    "Open at least one tab in the persistent Chrome window "
                    "(see com.morningbrief.chrome.plist) and try again - "
                    "a fresh browser context can't be created on a real "
                    "Chrome profile over CDP." % CDP_URL
                )
            context = browser.contexts[0]
            page = context.new_page()
            try:
                # domcontentloaded rather than networkidle: Readability
                # only needs the DOM, not every last ad/tracker request to
                # settle, and modern sites often never go fully idle.
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
            except Exception:
                pass  # partial load is still usually a real page by this point
            dismiss_cookie_banner(page)
            try:
                page.evaluate(SCROLL_SCRIPT)
            except Exception as err:
                print(f"Scroll pass failed for {url} (continuing anyway): {err}", file=sys.stderr)

            article = None
            try:
                page.add_script_tag(path=str(READABILITY_JS))
                article = page.evaluate(EXTRACT_SCRIPT)
            except Exception as err:
                print(f"Readability extraction failed for {url}: {err}", file=sys.stderr)

            if article:
                html = "<html><head><title>%s</title></head><body>%s</body></html>" % (
                    json.dumps(article["title"])[1:-1], article["content"]
                )
            else:
                html = page.content()
            page.close()
    except Exception as err:
        print(f"Could not fetch {url} via Chrome CDP at {CDP_URL}: {err}", file=sys.stderr)
        sys.exit(1)

    sys.stdout.write(html)


if __name__ == "__main__":
    main()
