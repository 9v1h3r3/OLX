import os
import json
import asyncio
import threading
import time
import requests
from flask import Flask
from datetime import datetime
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

RETRY_MAX = 2
RELOAD_INTERVAL = 3600
RESTART_DELAY = 3

SELF_URL = os.environ.get("SELF_URL")
IS_DEPLOY = os.environ.get("RENDER", "false").lower() == "true"

app = Flask(__name__)
state = {"sent": 0, "errors": 0, "last_reload": 0}


@app.route("/")
def home():
    return f"✅ Messenger Bot running — Sent: {state['sent']} | Errors: {state['errors']}"


# ======================================================
# LOGGING
# ======================================================
def log(msg, level="INFO"):
    print(f"[{datetime.now()}] [{level}] {msg}", flush=True)


# ======================================================
# SEND MESSAGES TO SINGLE CHAT
# ======================================================
async def send_messages_to_chat(tid, page, messages, prefix):
    # Open chat with retries
    for attempt in range(3):
        try:
            url = f"https://www.facebook.com/messages/e2ee/t/{tid}"
            log(f"Opening chat {tid} → {url}")
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            break
        except Exception as e:
            log(f"Chat open attempt {attempt+1} failed for {tid}: {e}", "WARN")
            if attempt == 2:
                state["errors"] += 1
                return

    selectors = [
        'div[aria-label="Type a message"]',
        'div[aria-label="Message"]',
        'div[role="textbox"]',
        'div[contenteditable="true"]',
        'textarea'
    ]

    for msg in messages:
        full_msg = f"{prefix} {msg}".strip()
        sent = False
        for attempt in range(RETRY_MAX):
            try:
                input_box = None
                for sel in selectors:
                    input_box = await page.query_selector(sel)
                    if input_box:
                        break

                if not input_box:
                    raise Exception("Input box not found")

                # Instant send: fill + Enter
                await input_box.fill(full_msg)
                await input_box.press("Enter")

                log(f"Sent to {tid}: {full_msg[:50]}")
                state["sent"] += 1
                sent = True
                await asyncio.sleep(0.2)  # minimal delay between messages
                break
            except Exception as e:
                log(f"Attempt {attempt+1} failed for {tid}: {e}", "WARN")
                state["errors"] += 1
                await asyncio.sleep(0.5)

        if not sent:
            log(f"Failed to send to {tid}: {full_msg[:50]}", "ERROR")


# ======================================================
# SEND MESSAGES TO ALL CHATS (PARALLEL)
# ======================================================
async def send_all_messages():
    if not IS_DEPLOY:
        log("⚠️ Build phase detected — messages will NOT be sent", "WARN")
        return

    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = [c for c in json.load(f) if "name" in c and "value" in c]
        if not cookies:
            log("No valid cookies found!", "WARN")
    except Exception as e:
        log(f"Failed to load cookies: {e}", "ERROR")
        return

    try:
        with open(TARGETS_FILE, "r", encoding="utf-8") as f:
            targets = [t.strip() for t in f if t.strip()]
        if not targets:
            log("No targets found!", "WARN")
    except Exception as e:
        log(f"Failed to load targets: {e}", "ERROR")
        return

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            messages = [m.strip() for m in f if m.strip()]
        if not messages:
            log("No messages found!", "WARN")
    except Exception as e:
        log(f"Failed to load messages: {e}", "ERROR")
        return

    prefix = ""
    if os.path.exists(PREFIX_FILE):
        try:
            prefix = open(PREFIX_FILE, "r", encoding="utf-8").read().strip()
        except Exception as e:
            log(f"Failed to read prefix: {e}", "WARN")

    async with async_playwright() as p:
        try:
            log("Launching browser...")
            browser = await p.chromium.launch(headless=HEADLESS, args=BROWSER_ARGS, channel="chrome")
        except Exception as e:
            log(f"Browser launch failed: {e}", "ERROR")
            return

        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()

        tasks = [send_messages_to_chat(tid, page, messages, prefix) for tid in targets]
        await asyncio.gather(*tasks)

        await browser.close()
        log("All message cycles completed.")


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

            log("Starting send_all_messages loop...")
            await send_all_messages()
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
