from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


def click_first(page, selectors):
    for selector in selectors:
        try:
            loc = page.locator(selector)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=5000)
                return selector
        except Exception:
            pass
    return None


def scrape(video_id: str, output: str):
    url = f"https://www.youtube.com/watch?v={video_id}&hl=es"
    result = {
        "video_id": video_id,
        "url": url,
        "success": False,
        "word_count": 0,
        "character_count": 0,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "diagnostics": [],
    }
    transcript = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            locale="es-ES",
            timezone_id="Europe/Madrid",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1200},
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
            body = page.locator("body").inner_text(timeout=10000)
            if "Sign in to confirm you’re not a bot" in body or "confirma que no eres un bot" in body.lower():
                result["diagnostics"].append("youtube_bot_challenge_visible")

            click_first(page, [
                'button:has-text("Aceptar todo")',
                'button:has-text("Accept all")',
                'button:has-text("Rechazar todo")',
                'button:has-text("Reject all")',
            ])
            page.wait_for_timeout(1500)

            click_first(page, [
                "#expand",
                'tp-yt-paper-button#expand',
                'button:has-text("más")',
                'button:has-text("more")',
            ])
            page.wait_for_timeout(1200)

            clicked = click_first(page, [
                'button:has-text("Mostrar transcripción")',
                'button:has-text("Show transcript")',
                'ytd-video-description-transcript-section-renderer button',
                'button[aria-label*="transcrip"]',
                'tp-yt-paper-button:has-text("transcrip")',
            ])
            result["diagnostics"].append("transcript_button=" + str(clicked))
            page.wait_for_timeout(3500)

            selectors = [
                "ytd-transcript-segment-renderer",
                "ytd-transcript-segment-view-model",
                "ytd-transcript-segment-list-renderer yt-formatted-string",
                'ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"] yt-formatted-string',
                '[class*="segment-text"]',
                '[class*="transcript-segment"]',
            ]
            texts = []
            seen = set()
            for selector in selectors:
                loc = page.locator(selector)
                count = loc.count()
                result["diagnostics"].append(f"{selector}={count}")
                for i in range(min(count, 5000)):
                    try:
                        txt = re.sub(r"\s+", " ", loc.nth(i).inner_text(timeout=1500)).strip()
                    except Exception:
                        continue
                    if not txt or txt in seen or len(txt) < 2:
                        continue
                    if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", txt):
                        continue
                    if txt.lower() in {"transcripción", "transcript", "mostrar transcripción", "show transcript"}:
                        continue
                    seen.add(txt)
                    texts.append(txt)
            if not texts:
                panel = page.locator('ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"]')
                result["diagnostics"].append(f"panel_count={panel.count()}")
                if panel.count():
                    try:
                        panel_text = re.sub(r"\s+", " ", panel.first.inner_text(timeout=3000)).strip()
                        result["diagnostics"].append("panel_text_prefix=" + panel_text[:500])
                    except Exception as exc:
                        result["diagnostics"].append("panel_text_error=" + type(exc).__name__)
            transcript = "\n".join(texts).strip()
            if transcript:
                result["success"] = True
                result["word_count"] = len(transcript.split())
                result["character_count"] = len(transcript)
                Path(output).write_text(transcript + "\n", encoding="utf-8")
            else:
                title = page.title()
                result["diagnostics"].append("page_title=" + title[:200])
        finally:
            context.close()
            browser.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["success"]:
        raise SystemExit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    scrape(args.video_id, args.output)


if __name__ == "__main__":
    main()
