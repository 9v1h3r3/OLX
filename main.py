import os
import json
import asyncio
import random
import threading
import time
import requests
import subprocess
from flask import Flask

# ======================================================
# 🧩 AUTO-INSTALL & BROWSER FIX FOR RENDER
# ======================================================
try:
    from playwright.async_api import async_playwright
    import shutil

    chromium_path = "/opt/render/.cache/ms-playwright"
    if not os.path.exists(chromium_path):
        print("[⚙️] Chromium not found — installing now...")
        subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)

except Exception:
    print("[⚙️] Installing Playwright + Chromium...")
    subprocess.run(["pip", "install", "playwright"], check=True)
    subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)
    from playwright.async_api import async_playwright

# ======================================================
# CONFIGURATION
# ======================================================
COOKIE_FILE = "cookies.json"
TARGETS_FILE = "targets.txt"
MESSAGES_FILE = "messages.txt"
PREFIX_FILE = "prefix.txt"

HEADLESS = True
BROWSER_ARGS = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]

DELAY_MIN = 3.0
DELAY_MAX = 5.0

SELF_URL = os.environ.get("SELF_URL")  # e.g. https://your-app.onrender.com/
PING_INTERVAL = 300     # 5 min
RELOAD_INTERVAL = 3600  # 1 hour reload
RESTART_DELAY = 5       # restart delay after crash

app = Flask(__name__)
state = {"sent": 0, "errors": 0, "last_reload": 0}


@app.route("/")
def home():
    return f"✅ Messenger Bot running — Sent: {state['sent']} | Errors: {state['errors']}"


# ======================================================
# MAIN MESSAGE SENDER
# ======================================================
async def send_messages():
    """Load all files and send messages continuously."""
    # Load cookies
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        cookies = [c for c in json.load(f) if "name" in c and "value" in c]

    # Load targets
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        targets = [t.strip() for t in f if t.strip()]

    # Load messages
    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        messages = [m.strip() for m in f if m.strip()]

    # Load prefix
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
                print(f"\n[💬] Opening chat with {tid}")
                await page.goto(url, timeout=60000)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)

                for msg in messages:
                    full_msg = f"{prefix} {msg}".strip()
                    success = False

                    for attempt in range(3):  # Retry 3 times
                        try:
                            selectors = [
                                'div[aria-label="Message"]',
                                'div[role="textbox"]',
                                'div[contenteditable="true"]',
                                'textarea'
                            ]

                            input_box = None
                            for sel in selectors:
                                el = await page.query_selector(sel)
                                if el:
                                    input_box = el
                                    break

                            if not input_box:
                                raise Exception("Message input box not found")

                            await input_box.click()
                            await input_box.fill(full_msg)
                            await input_box.press("Enter")
                            print(f"✅ Sent to {tid}: {full_msg[:60]}")
                            state["sent"] += 1
                            success = True
                            await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
                            break

                        except Exception as e:
                            print(f"[x] Send attempt {attempt + 1} failed: {e}")
                            state["errors"] += 1
                            await asyncio.sleep(1)

                    if not success:
                        print(f"[!] Failed to send to {tid}: {full_msg[:60]}")

            except Exception as e:
                print(f"[!] Chat open error for {tid}: {e}")
                state["errors"] += 1

        await browser.close()
        print("✅ Message cycle completed.")


# ======================================================
# FOREVER LOOP (NONSTOP)
# ======================================================
async def forever_loop():
    while True:
        try:
            now = time.time()
            if now - state["last_reload"] > RELOAD_INTERVAL:
                print("[♻️] Reloading data files...")
                state["last_reload"] = now

            await send_messages()
            print("[🔁] Restarting send loop...")
            await asyncio.sleep(RESTART_DELAY)

        except Exception as e:
            print(f"[💥] Fatal error: {e}")
            state["errors"] += 1
            print(f"[♻️] Restarting in {RESTART_DELAY}s...")
            await asyncio.sleep(RESTART_DELAY)


def async_runner():
    asyncio.run(forever_loop())


# ======================================================
# SELF-PING SYSTEM
# ======================================================
def self_ping():
    while True:
        if SELF_URL:
            try:
                requests.get(SELF_URL, timeout=10)
                print("[🔁] Self-ping OK.")
            except Exception:
                print("[⚠️] Self-ping failed.")
        time.sleep(PING_INTERVAL)


# ======================================================
# MAIN ENTRY POINT
# ======================================================
if __name__ == "__main__":
    threading.Thread(target=async_runner, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
