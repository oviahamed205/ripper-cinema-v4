"""
Interactive Browser Session Capture Module for unshorten-cli.

Launches a visible Chromium (Google Chrome / Edge / Camoufox) browser window,
allows the user to complete login or solve captchas, captures authenticated
session cookies (e.g. next-auth.session-token for OlaMovies/PayBase),
saves them persistently to ~/.ripper/olamovies_session.json, and cleanly closes the browser.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from rich.console import Console
from rich.panel import Panel
from rich import box

from .browser_bypass import find_camoufox_executable

console = Console()

CONFIG_DIR = Path.home() / ".ripper"
SESSION_FILE = CONFIG_DIR / "olamovies_session.json"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_saved_olamovies_cookies() -> Dict[str, str]:
    """Load previously saved OlaMovies session cookies if they exist."""
    if SESSION_FILE.exists():
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # Check env var
    env_cookie = os.environ.get("UNSHORTEN_OLAMOVIES_COOKIE", "").strip()
    if env_cookie:
        cookies = {}
        for part in env_cookie.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookies[k] = v
        return cookies

    return {}


def save_olamovies_cookies(cookies: Dict[str, str]) -> None:
    """Save captured OlaMovies session cookies to ~/.ripper/olamovies_session.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(cookies, indent=2), encoding="utf-8")

    # Also sync into config.json
    try:
        conf = {}
        if CONFIG_FILE.exists():
            conf = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        conf["olamovies_cookies"] = cookies
        if "next-auth.session-token" in cookies:
            conf["olamovies_session_token"] = cookies["next-auth.session-token"]
        elif "__Secure-next-auth.session-token" in cookies:
            conf["olamovies_session_token"] = cookies["__Secure-next-auth.session-token"]
        CONFIG_FILE.write_text(json.dumps(conf, indent=2), encoding="utf-8")
    except Exception:
        pass


async def capture_olamovies_session_interactively(
    target_url: str = "https://paybase.olamovies.mov/login?callback=https%3A%2F%2Flinks.olamovies.mov%2Fapi%2Fauth%2Fcallback",
    timeout: float = 180.0,
) -> Dict[str, str]:
    """
    Launch visible Chrome window, prompt the user to log in, listen for session cookies,
    save them persistently, and automatically close the browser.
    """
    console.print(
        Panel(
            "[bold bright_cyan]🔐 OLAMOVIES INTERACTIVE LOGIN ASSISTANT[/bold bright_cyan]\n\n"
            "[white]1. A visible Chrome browser window has been opened for you.[/white]\n"
            "[white]2. Please complete your login or solve captcha in the browser.[/white]\n"
            "[white]3. Once authenticated, this assistant will [bold green]automatically capture your session[/bold green],\n"
            "   save your credentials locally, and [bold green]close the browser[/bold green].[/white]",
            box=box.ROUNDED,
            border_style="bright_magenta",
            title="[bold yellow]⚡ Automated Session Capture[/bold yellow]",
        )
    )

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        console.print("[bold red]❌ Playwright is not installed.[/bold red]")
        return {}

    captured_cookies: Dict[str, str] = {}

    async with async_playwright() as p:
        browser = None
        context = None

        # Prefer system Google Chrome, then Edge, then Camoufox
        for ch in ("chrome", "msedge"):
            try:
                browser = await p.chromium.launch(channel=ch, headless=False)
                break
            except Exception:
                continue

        if browser is None:
            camoufox_exe = find_camoufox_executable()
            if camoufox_exe:
                try:
                    browser = await p.firefox.launch(executable_path=camoufox_exe, headless=False)
                except Exception:
                    pass

        if browser is None:
            console.print("[bold red]❌ No suitable Chromium or Camoufox browser found to launch GUI.[/bold red]")
            return {}

        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = await context.new_page()

        console.print(f"[bold cyan]🌐 Navigating to login portal...[/bold cyan]")
        try:
            await page.goto(target_url, timeout=45000)
        except Exception as e:
            console.print(f"[dim]Initial navigation notice: {e}[/dim]")

        started = time.time()
        with console.status("[bold yellow]Waiting for you to log in... (Browser will auto-close when logged in)[/bold yellow]"):
            while time.time() - started < timeout:
                try:
                    cookies = await context.cookies()
                    cookie_dict = {c["name"]: c["value"] for c in cookies}

                    # Check for session token markers
                    has_session = any(
                        name in cookie_dict
                        for name in (
                            "next-auth.session-token",
                            "__Secure-next-auth.session-token",
                            "session",
                            "user_session",
                        )
                    )

                    # Also check if page navigated to callback, profile, dashboard, or home
                    curr_url = page.url.lower()
                    if has_session or ("links.olamovies.mov" in curr_url and "login" not in curr_url):
                        captured_cookies = cookie_dict
                        console.print("\n[bold bright_green]✔ Successfully detected active authenticated session![/bold bright_green]")
                        break

                except Exception:
                    pass

                await asyncio.sleep(1.0)

        # Close browser immediately
        try:
            await context.close()
            await browser.close()
        except Exception:
            pass

    if captured_cookies:
        save_olamovies_cookies(captured_cookies)
        console.print(
            Panel(
                f"[bold green]✔ Authenticated session captured ({len(captured_cookies)} cookie(s))![/bold green]\n"
                f"[dim]Saved to: {SESSION_FILE}[/dim]\n"
                f"[bold cyan]Chrome closed. Ready to download and stream at peak performance![/bold cyan]",
                box=box.ROUNDED,
                border_style="green",
            )
        )
    else:
        console.print("[bold red]❌ Login timed out or no session cookies were detected.[/bold red]")

    return captured_cookies

