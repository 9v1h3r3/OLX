# send_min.py  -- minimal messenger sender (headless chromium)
# Auto-converts cookie.txt (raw cookie header) -> cookie.json if cookie.json missing
# With cookie checks, login verification, logging and status file
# USAGE: put cookie.txt (raw header) OR cookie.json (exported), plus targets.txt, message.txt, prefix.txt (optional)
# NOTE: Use only your own account cookies.

import os, json, time, urllib.parse, datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# CONFIG
COOKIE_JSON = "cookie.json"
COOKIE_TXT = "cookie.txt"   # raw header string file (one line)
TARGETS = "targets.txt"
MESSAGE = "message.txt"
PREFIX = "prefix.txt"
MAX_MESSAGES_PER_RUN = 50
VERIFY_WAIT = 10
HEADLESS = True
USER_DATA_DIR = "./chrome_profile"
FIXED_DELAY_SECONDS = 10

LOG_PATH = "sender.log"
STATUS_PATH = "status.json"

ESSENTIAL_COOKIES = ["c_user", "xs", "datr", "fr"]

def log(msg):
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def write_status(status_obj):
    try:
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(status_obj, f, indent=2)
    except Exception as e:
        log(f"Failed to write status.json: {e}")

# ---- cookie helpers ----
def parse_header_cookie_string(s):
    """
    Parse raw cookie header string: "name=val; name2=val2; ..." -> list of cookie dicts
    """
    out = []
    if not s:
        return out
    for part in [x.strip() for x in s.split(";") if x.strip()]:
        if "=" not in part:
            continue
        name, val = part.split("=", 1)
        name = name.strip()
        val = urllib.parse.unquote_plus(val.strip())
        cookie = {"name": name, "value": val, "domain": ".facebook.com", "path": "/"}
        out.append(cookie)
    return out

def save_cookies_as_json(cookies, path=COOKIE_JSON):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        log(f"cookie.json written with {len(cookies)} cookies.")
    except Exception as e:
        log(f"Failed to write cookie.json: {e}")

def load_cookies(path):
    """
    Load cookie.json format if exists. If not, but cookie.txt exists, convert it -> cookie.json and return.
    """
    # If cookie.json exists, load it
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log(f"Failed to parse {path}: {e}")
            data = []
        # support {"cookies": [...]} wrapper
        if isinstance(data, dict) and "cookies" in data:
            data = data["cookies"]
        cookies = []
        for it in data:
            if not isinstance(it, dict):
                continue
            name = it.get("name") or it.get("key")
            val = it.get("value") or it.get("val")
            if not name or val is None:
                continue
            cookie = {"name": str(name), "value": str(val)}
            if "domain" in it and it["domain"]:
                cookie["domain"] = it["domain"]
            if "path" in it and it["path"]:
                cookie["path"] = it["path"]
            if "expiry" in it:
                try:
                    cookie["expiry"] = int(it["expiry"])
                except Exception:
                    pass
            cookies.append(cookie)
        return cookies

    # else, try cookie.txt (raw header)
    if os.path.exists(COOKIE_TXT):
        try:
            with open(COOKIE_TXT, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            cookies = parse_header_cookie_string(raw)
            if cookies:
                # save as cookie.json for future runs
                save_cookies_as_json(cookies, path)
                return cookies
            else:
                log("cookie.txt parsed but no cookies found.")
                return []
        except Exception as e:
            log(f"Failed to read/parse {COOKIE_TXT}: {e}")
            return []
    # nothing found
    return []

def cookie_health_check(cookies):
    names = set([c.get("name") for c in cookies if c.get("name")])
    missing = [n for n in ESSENTIAL_COOKIES if n not in names]
    present = [n for n in ESSENTIAL_COOKIES if n in names]
    return {"present": present, "missing": missing, "count_total": len(cookies)}

# ---- selenium helpers ----
def normalize_target(raw):
    t = raw.strip()
    if not t: return ""
    if t.lower().startswith("http"): return t
    digits = "".join(ch for ch in t if ch.isdigit())
    if digits and len(digits) >= 6 and digits == t.replace(" ",""):
        return f"https://www.facebook.com/messages/e2ee/t/{digits}"
    return t

def create_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--single-process")
    opts.add_argument(f"--user-data-dir={USER_DATA_DIR}")
    prefs = {"profile.managed_default_content_settings.images":2}
    opts.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(60)
    return driver

def safe_add_cookie(driver, c):
    ccopy = dict(c)
    try:
        driver.add_cookie(ccopy); return True
    except Exception:
        c2 = {k:v for k,v in ccopy.items() if k not in ("domain",)}
        try:
            driver.add_cookie(c2); return True
        except Exception:
            if "domain" in ccopy and isinstance(ccopy["domain"], str) and ccopy["domain"].startswith("."):
                c3 = dict(ccopy); c3["domain"] = c3["domain"].lstrip(".")
                try:
                    driver.add_cookie(c3); return True
                except Exception:
                    pass
    return False

def open_conversation(driver, target, wait):
    t = normalize_target(target)
    if not t: return False
    if t.lower().startswith("http"):
        driver.get(t)
        time.sleep(1.0)
        # try E2EE banner click best-effort
        try:
            btns = [
                "//button[contains(.,'View end-to-end encrypted conversation')]",
                "//button[contains(.,'See end-to-end encrypted conversation')]"
            ]
            for xp in btns:
                try:
                    el = WebDriverWait(driver,2).until(EC.element_to_be_clickable((By.XPATH,xp)))
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.5)
                    break
                except Exception:
                    continue
        except Exception:
            pass
        try:
            wait.until(EC.presence_of_element_located((By.XPATH,"//div[@contenteditable='true' and @role='textbox']")), timeout=8)
            return True
        except Exception:
            return False
    else:
        driver.get("https://www.messenger.com/")
        time.sleep(1.0)
        try:
            search_xp = "//input[contains(@placeholder,'Search')]"
            s = WebDriverWait(driver,5).until(EC.element_to_be_clickable((By.XPATH,search_xp)))
            s.clear(); time.sleep(0.2); s.send_keys(t); time.sleep(1.0)
            first = "(//a[contains(@href,'/messages/t/')])[1]"
            el = driver.find_element(By.XPATH, first)
            driver.execute_script("arguments[0].click();", el)
            wait.until(EC.presence_of_element_located((By.XPATH,"//div[@contenteditable='true' and @role='textbox']")), timeout=6)
            return True
        except Exception:
            return False

def send_message(driver, msg, wait):
    try:
        inp_xp = "//div[@contenteditable='true' and @role='textbox']"
        el = wait.until(EC.presence_of_element_located((By.XPATH,inp_xp)), timeout=6)
        driver.execute_script("arguments[0].focus();", el)
        time.sleep(0.2)
        lines = msg.split("\n")
        for i, line in enumerate(lines):
            el.send_keys(line)
            if i < len(lines)-1:
                el.send_keys("\uE008")
        try:
            el.send_keys("\n")
        except Exception:
            pass
        time.sleep(0.6)
        return True
    except Exception:
        return False

def read_prefix(path):
    if not os.path.exists(path):
        return ""
    try:
        with open(path,"r",encoding="utf-8") as f:
            p = f.read().strip()
            if p:
                return p + " "
    except Exception:
        pass
    return ""

# ---- main loop ----
def main_loop():
    status = {
        "last_run": datetime.datetime.utcnow().isoformat() + "Z",
        "login_verified": False,
        "cookie_check": {},
        "document_cookie_snapshot": "",
        "sent": 0,
        "failed": 0,
        "details": []
    }

    # load message & targets
    if not os.path.exists(MESSAGE):
        log("Missing message.txt"); return
    if not os.path.exists(TARGETS):
        log("Missing targets.txt"); return
    with open(MESSAGE,'r',encoding='utf-8') as f: base_msg = f.read().strip()
    with open(TARGETS,'r',encoding='utf-8') as f: targets = [l.strip() for l in f if l.strip()]
    prefix_text = read_prefix(PREFIX)

    cookies = load_cookies(COOKIE_JSON)
    status["cookie_check"] = cookie_health_check(cookies)
    log(f"Cookie health check: present={status['cookie_check']['present']} missing={status['cookie_check']['missing']} count={status['cookie_check']['count_total']}")
    write_status(status)

    if not cookies:
        log("No cookies loaded. Place cookie.txt or cookie.json in the app folder.")
        return

    driver = create_driver()
    wait = WebDriverWait(driver,12)
    try:
        driver.get("https://www.facebook.com/")
        time.sleep(1.0)
        # add cookies
        added = 0
        for c in cookies:
            if "domain" not in c or not c.get("domain"): c["domain"] = ".facebook.com"
            c["value"] = urllib.parse.unquote_plus(str(c["value"]))
            if safe_add_cookie(driver,c): added += 1
        log(f"Attempted to add cookies: successful adds approx: {added}/{len(cookies)}")
        # verify login
        driver.get("https://www.messenger.com/")
        try:
            wait.until(EC.presence_of_element_located((By.XPATH,"//div[@contenteditable='true' and @role='textbox']")), timeout=VERIFY_WAIT)
            status["login_verified"] = True
            log("Login verified: message input found on messenger.")
        except Exception:
            status["login_verified"] = False
            log("Login NOT verified automatically. Messenger input not found (checkpoint/2FA likely).")
        # snapshot document.cookie
        try:
            doc_cookie = driver.execute_script("return document.cookie;")
            status["document_cookie_snapshot"] = doc_cookie
            log(f"document.cookie snapshot: { (doc_cookie[:300] + '...') if doc_cookie and len(doc_cookie)>300 else doc_cookie }")
        except Exception as e:
            log(f"Could not read document.cookie: {e}")

        write_status(status)

        sent = 0
        failed = 0
        for raw_t in targets:
            if sent >= MAX_MESSAGES_PER_RUN:
                log("Reached MAX_MESSAGES_PER_RUN limit.")
                break
            target = normalize_target(raw_t)
            log(f"Processing target: {raw_t} -> normalized: {target}")
            ok_open = open_conversation(driver, target, wait)
            detail = {"target": raw_t, "normalized": target, "opened": ok_open, "sent": False, "error": None}
            if not ok_open:
                detail["error"] = "open_failed"
                log(f"   ! Could not open conversation for {raw_t}")
                failed += 1
                status["details"].append(detail)
                write_status(status)
                time.sleep(1)
                continue
            msg = prefix_text + base_msg if prefix_text else base_msg
            ok_send = send_message(driver, msg, wait)
            if ok_send:
                log(f"   ✓ Message sent to {raw_t}")
                detail["sent"] = True
                sent += 1
            else:
                log(f"   ✗ Failed to send to {raw_t}")
                detail["error"] = "send_failed"
                failed += 1
            status["details"].append(detail)
            status["sent"] = sent
            status["failed"] = failed
            write_status(status)
            log(f"   Waiting fixed {FIXED_DELAY_SECONDS}s before next message...")
            time.sleep(FIXED_DELAY_SECONDS)
        log(f"Run finished. sent: {sent}, failed: {failed}")
    finally:
        try: driver.quit()
        except: pass
        status["last_run"] = datetime.datetime.utcnow().isoformat() + "Z"
        status["login_verified"] = status.get("login_verified", False)
        write_status(status)

if __name__ == "__main__":
    # infinite run with restart on error
    while True:
        try:
            main_loop()
        except Exception as e:
            log(f"Unhandled exception in main_loop: {e}")
        time.sleep(30)
