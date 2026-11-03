import asyncio
import os
import json
import random
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

SITES = [
    "https://kmmovies.pics/",
    "https://moviesbaba.lol/",
    "https://new.katmoviehd.top/",
    "https://new.katdrama.my/",
    "https://fojik.site/",
    "https://1vegamovies.me/",
    "https://v5.olamovies.mov/",
    "https://olamovies.dad/",
    "https://mkvbase.site/",
    "https://mkvdrama.net/",
    "https://top.xdmovies.wtf/",
    "https://ciniverse.site/",
    "https://worldfree4u.gd/",
    "https://uhdmovies.autos/",
    "https://hdmovieshub.fyi/",
    "https://hindmovie.fit/",
]

SCREENSHOT_DIR = r"D:\prework\final work\ripper\test_results\screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

async def run_playwright_test():
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ]
        )

        for url in SITES:
            domain = url.replace("https://", "").replace("http://", "").strip("/").replace("/", "_").replace(".", "_")
            print(f"\n[*] Playwright testing: {url}")
            
            ua = random.choice(USER_AGENTS)
            vp = random.choice(VIEWPORTS)
            context = await browser.new_context(
                user_agent=ua,
                viewport=vp,
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = await context.new_page()
            await stealth_async(page)

            console_logs = []
            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

            network_media = []
            page.on("response", lambda resp: network_media.append(resp.url) if any(ext in resp.url.lower() for ext in (".mkv", ".mp4", ".zip", ".rar", ".srt", ".ass")) else None)

            site_data = {
                "target_url": url,
                "final_url": url,
                "title": "",
                "status": "error",
                "screenshot_path": None,
                "console_logs_count": 0,
                "network_media_count": 0,
                "cookies_count": 0,
                "error": None
            }

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                
                site_data["final_url"] = page.url
                site_data["title"] = await page.title()
                site_data["status"] = "success"
                
                # Screenshot
                shot_path = os.path.join(SCREENSHOT_DIR, f"{domain}.png")
                await page.screenshot(path=shot_path, full_page=False)
                site_data["screenshot_path"] = shot_path
                
                # Cookies
                cookies = await context.cookies()
                site_data["cookies_count"] = len(cookies)
                site_data["console_logs_count"] = len(console_logs)
                site_data["network_media_count"] = len(network_media)

                print(f"    [+] Page Title: {site_data['title'][:40]} | Cookies: {len(cookies)} | Shot: {shot_path}")
            except Exception as exc:
                site_data["error"] = str(exc)
                print(f"    [-] Error: {exc}")
            finally:
                await context.close()
            
            results[url] = site_data

        await browser.close()

    out_file = r"D:\prework\final work\ripper\test_results\playwright_run.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\n[OK] Playwright testing completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_playwright_test())
