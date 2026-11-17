# ================= IMPORTS =================
import csv
import time
import json
import random
import pickle
import re
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException


LOGIN_CSV = "login.csv"
HEADLESS = False
LOGIN_WAIT_TIMEOUT = 120   # longer wait for FB security redirects


# ================= DRIVER =================
def create_driver():
    options = webdriver.ChromeOptions()

    if HEADLESS:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    return driver


# ================= COOKIE HELPERS =================
def safe_cookie_name(identifier):
    identifier = identifier.strip().lower()
    identifier = identifier.replace("@", "_at_").replace(".", "_")
    identifier = re.sub(r"[^a-z0-9_]+", "", identifier)
    return f"{identifier}_cookies.pkl"


def cookie_file(identifier):
    return Path(safe_cookie_name(identifier))


def save_cookies(driver, identifier):
    if "facebook.com" not in driver.current_url.lower():
        print("[!] Not saving cookies — homepage not loaded")
        return

    cookies = driver.get_cookies()
    if not cookies:
        print("[!] No cookies to save")
        return

    pkl = cookie_file(identifier)

    with open(pkl, "wb") as f:
        pickle.dump(cookies, f)

    with open(pkl.with_suffix(".json"), "w", encoding="utf-8") as f:
        json.dump(cookies, f)

    print("[✓] Cookies refreshed & saved")


def session_active(driver):
    """Robust login detection"""
    try:
        names = [c['name'] for c in driver.get_cookies()]
    except:
        names = []

    url = driver.current_url.lower()

    if "c_user" in names or "xs" in names:
        return True

    if "login" not in url and "checkpoint" not in url:
        return True

    if "facebook.com/home" in url:
        return True

    return False


def load_cookies(driver, identifier):
    pkl = cookie_file(identifier)
    json_file = pkl.with_suffix(".json")

    if not pkl.exists() and not json_file.exists():
        return False

    source = pkl if pkl.exists() else json_file
    print(f"[i] Loading cookies from {source.name}")

    driver.get("https://www.facebook.com/")
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(3)

    cookies = pickle.load(open(source, "rb")) if source.suffix == ".pkl" else json.load(open(source))

    for c in cookies:
        try:
            if "expiry" in c:
                c["expiry"] = int(c["expiry"])
            driver.add_cookie(c)
        except:
            continue

    driver.get("https://www.facebook.com/")
    time.sleep(6)

    return session_active(driver)


# ================= UTILS =================
def type_like_human(el, text):
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(0.08, 0.22))


def safe_click_login(driver):
    try:
        driver.find_element(By.NAME, "login").click()
    except:
        driver.find_element(By.NAME, "pass").send_keys(Keys.ENTER)


def wait_for_login(driver, timeout=LOGIN_WAIT_TIMEOUT):
    print("[i] Waiting for login completion...")
    end = time.time() + timeout

    while time.time() < end:
        if session_active(driver):
            return True
        time.sleep(2)

    return False


# ================= LOGIN =================
def login(identifier, password):
    print(f"[•] Login start → {identifier}")
    driver = create_driver()

    # TRY COOKIE LOGIN
    if load_cookies(driver, identifier):
        print("[✓] Cookies loaded — proceeding without verification")

        # give FB a moment to render UI
        time.sleep(5)

        return driver

    print("[i] Cookie login incomplete — proceeding with login")

    driver.get("https://www.facebook.com/login")

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.NAME, "email"))
        )
    except TimeoutException:
        if session_active(driver):
            return driver
        driver.quit()
        return None

    email = driver.find_element(By.NAME, "email")
    passwd = driver.find_element(By.NAME, "pass")

    type_like_human(email, identifier)
    time.sleep(1)
    type_like_human(passwd, password)
    time.sleep(1)

    safe_click_login(driver)

    print("[i] Complete any verification if prompted...")
    time.sleep(25)

    if wait_for_login(driver):
        print("[✓] Login successful")

        time.sleep(5)
        if session_active(driver):
            save_cookies(driver, identifier)

        return driver

    print("[!] Login not confirmed — waiting extra time...")
    time.sleep(25)

    if session_active(driver):
        print("[✓] Login confirmed after delay")
        save_cookies(driver, identifier)
        return driver

    print("[!] Login verification not confirmed — continuing anyway")
    return driver


# ================= MAIN =================
def main():
    accounts = []

    with open(LOGIN_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = row.get("email", "").strip()
            phone = row.get("phoneno", "").strip()
            password = row.get("password", "").strip()
            if password:
                accounts.append((email or phone, password))

    if not accounts:
        print("[!] No accounts found")
        return None

    identifier, password = accounts[0]

    driver = login(identifier, password)

    if driver:
        print("[✓] Driver ready")
        return driver   # ✅ IMPORTANT
    else:
        print("[!] Driver failed to start")
        return None


if __name__ == "__main__":
    driver = main()