import os
import json
import threading
import asyncio
import time
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from playwright.async_api import async_playwright

BASE = Path(__file__).parent
DATA_DIR = BASE / 'data'
SESSIONS_DIR = DATA_DIR / 'sessions'
LOGS_DIR = DATA_DIR / 'logs'
USERS_FILE = DATA_DIR / 'users.json'

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# --- Initialize sample users.json if missing (passwords hashed) ---
if not USERS_FILE.exists():
    sample = {
        "admin": generate_password_hash("admin123"),
        "user1": generate_password_hash("password1")
    }
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(sample, f, indent=2)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.urandom(24)

# Track active bots and control flags
ACTIVE = {}  # username -> bool
THREADS = {}

# ---------------- Cookie parsing helpers ----------------
import re

def try_parse_json(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def parse_netscape(text):
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith('#')]
    out = []
    for line in lines:
        parts = re.split(r'\s+', line)
        if len(parts) >= 7:
            domain, flag, path, secure, expires, name, value = parts[:7]
            out.append({
                'name': name,
                'value': value,
                'domain': domain or '.facebook.com',
                'path': path or '/',
                'expires': int(expires) if expires.isdigit() else 0,
                'httpOnly': False,
                'secure': secure.lower() in ('true','1','yes')
            })
    return out if out else None


def parse_raw_header(text):
    parts = [p.strip() for p in text.split(';') if '=' in p]
    out = []
    for p in parts:
        k, v = p.split('=', 1)
        out.append({'name': k.strip(), 'value': v.strip(), 'domain': '.facebook.com', 'path': '/', 'expires': 0, 'httpOnly': False, 'secure': False})
    return out if out else None


def convert_to_playwright(cookies):
    if isinstance(cookies, dict):
        return [{'name': k, 'value': v, 'domain': '.facebook.com', 'path': '/', 'expires': 0, 'httpOnly': False, 'secure': False} for k,v in cookies.items()]
    if isinstance(cookies, list):
        out = []
        for c in cookies:
            if 'name' in c and 'value' in c:
                out.append({
                    'name': c['name'],
                    'value': c['value'],
                    'domain': c.get('domain', '.facebook.com'),
                    'path': c.get('path', '/'),
                    'expires': int(c.get('expires', 0) or 0),
                    'httpOnly': bool(c.get('httpOnly', False)),
                    'secure': bool(c.get('secure', False))
                })
        return out
    return None


def auto_convert(text):
    if not text:
        return None
    j = try_parse_json(text)
    if j:
        conv = convert_to_playwright(j)
        if conv: return conv
    nets = parse_netscape(text)
    if nets: return convert_to_playwright(nets)
    raw = parse_raw_header(text)
    if raw: return convert_to_playwright(raw)
    return None

# ---------------- Playwright worker ----------------
async def bot_worker(username, cookies_list, prefix, messages, targets, logger):
    logger(f"[+] Starting Playwright for {username}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = await browser.new_context()
            await context.add_cookies(cookies_list)
            page = await context.new_page()
            await page.goto('https://www.facebook.com/')
            await asyncio.sleep(2)
            if 'login' in page.url.lower():
                logger('[!] Cookies invalid — login required')
                await browser.close()
                return

            for tid in targets:
                if not ACTIVE.get(username):
                    logger('[!] Stop requested, breaking')
                    break
                url = f'https://www.facebook.com/messages/e2ee/t/{tid}'
                logger(f"[💬] Opening {tid}")
                await page.goto(url)
                await asyncio.sleep(2)
                for msg in messages:
                    if not ACTIVE.get(username):
                        break
                    full = (prefix + ' ' + msg).strip()
                    try:
                        input_box = await page.query_selector('div[role="textbox"]')
                        if not input_box:
                            logger('[!] Input box missing')
                            continue
                        await page.evaluate(f"navigator.clipboard.writeText({json.dumps(full)})")
                        await input_box.click()
                        await page.keyboard.down('Control')
                        await page.keyboard.press('V')
                        await page.keyboard.up('Control')
                        send_btn = await page.query_selector('[aria-label="Send"], [aria-label="Press Enter to send"]')
                        if send_btn:
                            await send_btn.click()
                        else:
                            await page.keyboard.press('Enter')
                        logger(f"✅ Sent to {tid}: {full[:80]}")
                        await asyncio.sleep(2 + (time.time() % 2))
                    except Exception as e:
                        logger(f"[x] Error sending: {e}")

            await browser.close()
            logger(f"[✔] Finished for {username}")
    except Exception as e:
        logger(f"[x] Playwright exception: {e}")

# Thread wrapper
def start_thread(username, cookies_list, prefix, messages, targets):
    def logger(msg):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f"{ts} {msg}\n"
        with open(LOGS_DIR / f"{username}.log", 'a', encoding='utf-8') as f:
            f.write(line)
        print(line, end='')

    ACTIVE[username] = True
    asyncio.run(bot_worker(username, cookies_list, prefix, messages, targets, logger))
    ACTIVE[username] = False

# ---------------- Routes ----------------
@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('panel'))
    return render_template('panel.html', user=None)

@app.route('/panel')
def panel():
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('panel.html', user=session['user'])

@app.route('/login', methods=['POST'])
def login():
    u = request.form.get('username')
    pw = request.form.get('password')
    if not u or not pw:
        return 'Missing', 400
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    hashed = users.get(u)
    if hashed and check_password_hash(hashed, pw):
        session['user'] = u
        return redirect(url_for('panel'))
    return 'Invalid credentials', 401

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/api/convert_cookies', methods=['POST'])
def api_convert_cookies():
    data = request.json or {}
    text = data.get('text','')
    conv = auto_convert(text)
    if not conv:
        return jsonify({'ok': False, 'error': 'Unable to parse cookies'}), 400
    return jsonify({'ok': True, 'cookies': conv})

@app.route('/api/start', methods=['POST'])
def api_start():
    if 'user' not in session:
        return jsonify({'ok': False, 'error':'Not authenticated'}), 401
    user = session['user']
    payload = request.json or {}
    cookies = payload.get('cookies')
    prefix = payload.get('prefix','')
    messages = [m for m in payload.get('messages',[]) if m.strip()]
    targets = [t for t in payload.get('targets',[]) if t.strip()]
    if ACTIVE.get(user):
        return jsonify({'ok': False, 'error':'Bot already running'}), 400
    if not cookies:
        return jsonify({'ok': False, 'error':'Cookies required'}), 400
    # save session
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SESSIONS_DIR / f"{user}.json", 'w', encoding='utf-8') as f:
        json.dump({'cookies': cookies, 'prefix': prefix, 'messages': messages, 'targets': targets}, f, indent=2)

    t = threading.Thread(target=start_thread, args=(user, cookies, prefix, messages, targets), daemon=True)
    THREADS[user] = t
    t.start()
    return jsonify({'ok': True})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    if 'user' not in session:
        return jsonify({'ok': False, 'error':'Not authenticated'}), 401
    user = session['user']
    ACTIVE[user] = False
    return jsonify({'ok': True})

@app.route('/api/status')
def api_status():
    if 'user' not in session:
        return jsonify({'running': False})
    user = session['user']
    running = bool(ACTIVE.get(user))
    return jsonify({'running': running})

@app.route('/api/logs')
def api_logs():
    if 'user' not in session:
        return jsonify({'ok': False, 'error':'Not authenticated'}), 401
    user = session['user']
    logf = LOGS_DIR / f"{user}.log"
    if not logf.exists():
        return jsonify({'ok': True, 'lines': []})
    text = logf.read_text(encoding='utf-8')
    lines = text.splitlines()[-200:]
    return jsonify({'ok': True, 'lines': lines})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
