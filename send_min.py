# send_min.py  -- minimal messenger sender (headless chromium)
# USAGE: place (or provide via env) cookie.json, targets.txt, message.txt, optional prefix.txt in same folder
# NOTE: Use only your own account cookies.

import os, json, time, urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# CONFIG (tune if needed)
COOKIE_JSON = "cookie.json"
TARGETS = "targets.txt"
MESSAGE = "message.txt"
PREFIX = "prefix.txt"           # optional: if exists its content is prepended to each message
MAX_MESSAGES_PER_RUN = 50
VERIFY_WAIT = 10
HEADLESS = True
USER_DATA_DIR = "./chrome_profile"  # optional, helps persist session; mount as volume in container

# Fixed delay between messages (user requested): 10 seconds
FIXED_DELAY_SECONDS = 10

def rnd(a=1.0,b=3.0): 
    # kept for minor internal waits; main inter-message delay is fixed
    import random
    return random.uniform(a,b)

def load_cookies(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path,'r',encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return []
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    cookies=[]
    for it in data:
        if not isinstance(it, dict): continue
        name = it.get("name") or it.get("key")
        val = it.get("value") or it.get("val")
        if not name or val is None: continue
        cookie = {"name": str(name), "value": str(val)}
        if "domain" in it: cookie["domain"]=it["domain"]
        if "path" in it: cookie["path"]=it["path"]
        if "expiry" in it:
            try:
                cookie["expiry"]=int(it["expiry"])
            except Exception:
                pass
        cookies.append(cookie)
    return cookies

def parse_header_cookie_string(s):
    out=[]
    import urllib.parse
    for p in [x.strip() for x in s.split(";") if x.strip()]:
        if "=" not in p: continue
        name,val = p.split("=",1)
        out.append({"name":name.strip(),"value":urllib.parse.unquote_plus(val.strip()),"domain":".facebook.com","path":"/"})
    return out

def normalize_target(raw):
    t = raw.strip()
    if not t: return ""
    if t.lower().startswith("http"): return t
    digits = "".join(ch for ch in t if ch.isdigit())
    if digits and len(digits)>=6 and digits == t.replace(" ",""):
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
    # allow Selenium to auto-detect chromedriver (provided in container)
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(60)
    return driver

def safe_add_cookie(driver,c):
    ccopy = dict(c)
    try:
        driver.add_cookie(ccopy); return True
    except Exception:
        c2 = {k:v for k,v in ccopy.items() if k not in ("domain",)}
        try:
            driver.add_cookie(c2); return True
        except Exception:
            if "domain" in ccopy and isinstance(ccopy["domain"],str) and ccopy["domain"].startswith("."):
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
        # try to click e2ee banner if present (best-effort)
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
        time.sleep(rnd(0.6,1.2))
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
                return p + " "  # add trailing space separating prefix and message
    except Exception:
        pass
    return ""

def main_loop():
    # load files
    if not os.path.exists(MESSAGE):
        print("Missing message.txt"); return
    if not os.path.exists(TARGETS):
        print("Missing targets.txt"); return
    with open(MESSAGE,'r',encoding='utf-8') as f: base_msg = f.read().strip()
    with open(TARGETS,'r',encoding='utf-8') as f: targets = [l.strip() for l in f if l.strip()]

    prefix_text = read_prefix(PREFIX)
    cookies = load_cookies(COOKIE_JSON)

    driver = create_driver()
    wait = WebDriverWait(driver,12)
    try:
        driver.get("https://www.facebook.com/")
        time.sleep(1.0)
        added=0
        for c in cookies:
            if "domain" not in c or not c.get("domain"): c["domain"] = ".facebook.com"
            c["value"] = urllib.parse.unquote_plus(str(c["value"]))
            if safe_add_cookie(driver,c): added+=1
        print("Cookies added:", added)
        driver.get("https://www.messenger.com/")
        try:
            wait.until(EC.presence_of_element_located((By.XPATH,"//div[@contenteditable='true' and @role='textbox']")), timeout=VERIFY_WAIT)
            print("Logged in (input found).")
        except Exception:
            print("Login not auto-verified; check UI for checkpoint.")
        sent=0
        for t in targets:
            if sent>=MAX_MESSAGES_PER_RUN: break
            print("->", t)
            if not open_conversation(driver,t,wait):
                print("   cannot open:", t); time.sleep(1); continue
            # build message with optional prefix
            msg = prefix_text + base_msg if prefix_text else base_msg
            if send_message(driver,msg,wait):
                print("   sent")
                sent+=1
            else:
                print("   failed to send")
            # fixed 10 second delay as requested
            print(f"   waiting fixed {FIXED_DELAY_SECONDS}s before next message...")
            time.sleep(FIXED_DELAY_SECONDS)
        print("Run finished. sent:", sent)
    finally:
        try: driver.quit()
        except: pass

if __name__ == "__main__":
    # simple infinite run with sleep & restart on exception
    while True:
        try:
            main_loop()
        except Exception as e:
            print("Error:", e)
        # sleep before next run to avoid tight loop
        time.sleep(30)
