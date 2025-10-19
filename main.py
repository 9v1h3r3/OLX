import os
import json
import asyncio
import random
import threading
import time
import requests
from flask import Flask
from playwright.async_api import async_playwright

# ===========================================
# CONFIG
# ===========================================
COOKIE_FILE = "cookies.json"
TARGETS_FILE = "targets.txt"
MESSAGES_FILE = "messages.txt"
PREFIX_FILE = "prefix.txt"

HEADLESS = True
BROWSER_ARGS = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]

DELAY_MIN = 3
DELAY_MAX = 5

SELF_URL = os.environ.get("SELF_URL")  # e.g. https://your-app.onrender.com/
RELOAD_INTERVAL = 3600  # reload data every hour
WATCHDOG_INTERVAL = 60  # supervisor health check every 60s
RESTART_DELAY = 5       # seconds between auto restarts on crash

# ===========================================
app = Flask(__name__)
state = {"running": False, "last_error": None, "sent": 0, "last_reload": 0}


@app.route("/")
def home():
    return "✅ 365-Day Messenger Bot active!"


# ===========================================
async def run_bot_once():
    """Main send loop — runs once, supervisor will restart."""
    print("[+] Starting Playwright bot loop…")

    # Load data
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = [c for c in json.load(f) if "name" in c and "value" in c]

    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        targets = [t.strip() for t in f if t.strip()]

    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        messages = [m.strip() for m in f if m.strip()]

    prefix = ""
    if os.path.exists(PREFIX_FILE):
        prefix = open(PREFIX_FILE, "r", encoding="utf-8").read().strip()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, args=BROWSER_ARGS)
        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()

        for tid in targets:
            try:
                url = f"https://www.facebook.com/messages/e2ee/t/{tid}"
                print(f"\n[💬] Opening chat {tid}")
                await page.goto(url)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)

                for msg in messages:
                    full_msg = f"{prefix} {msg}".strip()
                    try:
                        input_box = await page.query_selector('div[contenteditable="true"]')
                        if not input_box:
                            raise Exception("No input box")
                        await input_box.click()
                        await input_box.fill(full_msg)
                        await input_box.press("Enter")
                        print(f"✅ Sent to {tid}: {full_msg[:60]}")
                        state["sent"] += 1
                        await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
                    except Exception as e:
                        print(f"[x] Message error: {e}")
                        await asyncio.sleep(1)
            except Exception as e:
                print(f"[!] Thread error for {tid}: {e}")

        await browser.close()
        print("\n✅ Loop complete (will auto-restart).")


# ===========================================
async def supervisor_loop():
    """Keeps bot alive 24/7, restarts on crash, reloads files hourly."""
    while True:
        try:
            # Reload data hourly
            now = time.time()
            if now - state["last_reload"] > RELOAD_INTERVAL:
                print("[♻️] Reloading data files…")
                state["last_reload"] = now

            state["running"] = True
            await run_bot_once()
            print("[⏳] Restarting main loop after short delay…")
            await asyncio.sleep(RESTART_DELAY)

        except Exception as e:
            state["last_error"] = str(e)
            print(f"[💥] Bot crashed: {e}")
            print(f"[♻️] Restarting in {RESTART_DELAY}s…")
            await asyncio.sleep(RESTART_DELAY)


def async_thread_runner():
    asyncio.run(supervisor_loop())


# ===========================================
def watchdog_thread():
    """Self-ping + health monitor for 365-day uptime."""
    while True:
        try:
            if SELF_URL:
                requests.get(SELF_URL, timeout=10)
                print("[🩺] Pinged self to keep alive.")
        except Exception:
            pass
        time.sleep(WATCHDOG_INTERVAL)


# ===========================================
if __name__ == "__main__":
    # Start background bot & watchdog
    threading.Thread(target=async_thread_runner, daemon=True).start()
    threading.Thread(target=watchdog_thread, daemon=True).start()

    # Flask server (for Render uptime)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
