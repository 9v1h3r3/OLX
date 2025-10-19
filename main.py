import os
import json
import asyncio
import random
import threading
import time
import requests
import subprocess
from flask import Flask
from datetime import datetime

# ======================================================
# 🧩 AUTO-INSTALL & CHROMIUM CHECK
# ======================================================
chromium_cache_path = "/opt/render/.cache/ms-playwright/chromium"

if not os.path.exists(chromium_cache_path):
    print(f"[{datetime.now()}] [⚙️] Chromium not found — installing...", flush=True)
    subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)
else:
    print(f"[{datetime.now()}] [ℹ️] Chromium already installed, skipping download.", flush=True)

from playwright.async_api import async_playwright

# ======================================================
# CONFIG
# ======================================================
COOKIE_FILE = "cookies.json"
TARGETS_FILE = "targets.txt"
MESSAGES_FILE = "messages.txt"
PREFIX_FILE = "prefix.txt"

HEADLESS = True
BROWSER_ARGS = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]

DELAY_MIN = 3.0
DELAY_MAX = 5.0
RETRY_MAX = 5
RELOAD_INTERVAL = 3600
RESTART_DELAY = 5

SELF_URL = os.environ.get("SELF_URL")

app = Flask(__name__)
state = {"sent": 0, "errors": 0, "last_reload": 0}


@app.route("/")
def home():
    return f"✅ Messenger Bot running — Sent: {state['sent']} | Errors: {state['errors']}"


# ======================================================
# UTILS
# ======================================================
def log(msg, level="INFO"):
    print(f"[{datetime.now()}] [{level}] {msg}", flush=True)


# ======================================================
# SEND MESSAGES
# ======================================================
async def send_messages():
    log("Loading cookies, targets, messages...")
    # Load cookies
    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = [c for c in json.load(f) if "name" in c and "value" in c]
        if not cookies:
            log("No valid cookies found!", "WARN")
    except Exception as e:
        log(f"Failed to load cookies: {e}", "ERROR")
        return

    # Load targets
    try:
        with open(TARGETS_FILE, "r", encoding="utf-8") as f:
            targets = [t.strip() for t in f if t.strip()]
        if not targets:
            log("No targets found!", "WARN")
    except Exception as e:
        log(f"Failed to load targets: {e}", "ERROR")
        return

    # Load messages
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            messages = [m.strip() for m in f if m.strip()]
        if not messages:
            log("No messages found!", "WARN")
    except Exception as e:
        log(f"Failed to load messages: {e}", "ERROR")
        return

    # Load prefix
    prefix = ""
    if os.path.exists(PREFIX_FILE):
        try:
            prefix = open(PREFIX_FILE, "r", encoding="utf-8").read().strip()
        except Exception as e:
            log(f"Failed to read prefix: {e}", "WARN")

    async with async_playwright() as p:
        try:
            log("Launching browser...")
            browser = await p.chromium.launch(headless=HEADLESS, args=BROWSER_ARGS)
        except Exception as e:
            log(f"Browser launch failed: {e}", "ERROR")
            return

        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()

        for tid in targets:
            chat_loaded = False
            for page_attempt in range(3):
                try:
                    url = f"https://www.facebook.com/messages/e2ee/t/{tid}"
                    log(f"Opening chat {tid} → {url}")
                    await page.goto(url, timeout=60000)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(5)
                    chat_loaded = True
                    break
                except Exception as e:
                    log(f"Chat load attempt {page_attempt+1} failed for {tid}: {e}", "WARN")
                    await asyncio.sleep(2)

            if not chat_loaded:
                log(f"Failed to open chat {tid} after 3 attempts", "ERROR")
                state["errors"] += 1
                continue

            for msg in messages:
                full_msg = f"{prefix} {msg}".strip()
                success = False
                for attempt in range(RETRY_MAX):
                    try:
                        selectors = [
                            'div[aria-label="Type a message"]',
                            'div[aria-label="Message"]',
                            'div[role="textbox"]',
                            'div[contenteditable="true"]',
                            'textarea'
                        ]
                        input_box = None
                        for sel in selectors:
                            try:
                                input_box = await page.query_selector(sel)
                                if input_box:
                                    break
                            except Exception:
                                continue
                        if not input_box:
                            raise Exception("Input box not found")

                        await input_box.scroll_into_view_if_needed()
                        await input_box.click(force=True)
                        await page.type(sel, full_msg, delay=50)
                        await page.keyboard.press("Enter")

                        log(f"Sent to {tid}: {full_msg[:60]}")
                        state["sent"] += 1
                        success = True
                        await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
                        break
                    except Exception as e:
                        log(f"Attempt {attempt+1} failed for {tid}: {e}", "WARN")
                        state["errors"] += 1
                        await asyncio.sleep(1)

                if not success:
                    log(f"Failed to send to {tid}: {full_msg[:60]}", "ERROR")

        await browser.close()
        log("Message cycle completed.")


# ======================================================
# FOREVER LOOP
# ======================================================
async def forever_loop():
    while True:
        try:
            now = time.time()
            if now - state["last_reload"] > RELOAD_INTERVAL:
                log("Reloading files...")
                state["last_reload"] = now

            log("Starting send_messages loop...")
            await send_messages()
            log("Loop finished. Restarting...")
            await asyncio.sleep(RESTART_DELAY)
        except Exception as e:
            log(f"Fatal error in forever_loop: {e}", "ERROR")
            state["errors"] += 1
            await asyncio.sleep(RESTART_DELAY)


def async_runner():
    try:
        log("Async runner starting...")
        asyncio.run(forever_loop())
    except Exception as e:
        log(f"Async loop crashed: {e}", "ERROR")


# ======================================================
# SELF-PING
# ======================================================
def self_ping():
    while True:
        if SELF_URL:
            try:
                requests.get(SELF_URL, timeout=10)
                log("Self-ping OK.")
            except Exception:
                log("Self-ping failed.", "WARN")
        time.sleep(300)


# ======================================================
# MAIN
# ======================================================
if __name__ == "__main__":
    threading.Thread(target=async_runner, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    log(f"Flask server starting on port {port}...")
    app.run(host="0.0.0.0", port=port)
