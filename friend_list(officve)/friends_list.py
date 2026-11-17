import csv
import time
import random
import re
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────

_FB_NAV_PATH_RE = re.compile(
    r"facebook\.com/"
    r"(friends|events|groups|pages|marketplace|gaming|watch|memories|saved|help"
    r"|notifications|settings|privacy|ads|business|donate|fundraisers|offers"
    r"|stories|reels|live|jobs|professional_dashboard)",
    re.IGNORECASE,
)

_SKIP_WORDS = [
    # navigation & UI
    "friends", "mutual", "recently", "added", "see all",
    "followers", "following", "photos", "about", "groups",
    "videos", "reels", "birthdays", "suggestions", "filter",
    "settings", "home", "menu", "notifications",

    # institutions & pages (not profiles)
    "university", "college", "school", "institute",
    "hospital", "restaurant", "company",

    # facebook UI labels
    "recently added", "mutual friends",
    "people you may know"
]

_SKIP_WORDS_LOWER = [w.lower() for w in _SKIP_WORDS]

def is_valid_friend_name(name):
    if not name:
        return False

    name = name.strip()
    lower = name.lower()

    # skip noise words
    if any(word in lower for word in _SKIP_WORDS):
        return False

    # remove counts like "108 friends"
    if re.search(r"\d+\s*(friends|mutual)", lower):
        return False

    # remove entries like "13 mutual friends"
    if "mutual friends" in lower:
        return False

    # must contain letters (real names)
    if not re.search(r"[a-zA-Z\u0600-\u06FF]", name):
        return False

    # real names usually have at least 2 words
    if len(name.split()) < 2:
        return False

    if len(name) < 3:
        return False

    return True

def extract_fbid_from_url(url):
    if not url:
        return ""
    m = re.search(r"id=(\d+)", url)
    if m:
        return m.group(1)
    return url.split("facebook.com/")[-1].split("?")[0].rstrip("/")

def normalize_profile_url(url):
    return url.split("?")[0].rstrip("/")

# ─────────────────────────────────────────────
# ⚡ ULTRA-FAST FRIEND SCRAPER
# ─────────────────────────────────────────────

def scrape_friends_fast(driver, profile_url):

    if "profile.php" in profile_url:
        friends_url = profile_url.split("&sk=")[0] + "&sk=friends"
    else:
        friends_url = profile_url.rstrip("/") + "/friends"

    print(f"   → Loading: {friends_url}")
    driver.get(friends_url)

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    seen = set()
    friends = []

    last_height = 0
    stable = 0

    while True:

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='facebook.com']")

        new_found = 0

        for a in anchors:
            try:
                url = a.get_attribute("href")
                name = a.text.strip()

                if not url or not name:
                    continue
                if not is_valid_friend_name(name):
                    continue
                if _FB_NAV_PATH_RE.search(url):
                    continue

                fbid = extract_fbid_from_url(url)

                if fbid in seen:
                    continue

                seen.add(fbid)
                friends.append({
                    "name": name,
                    "url": url,
                    "fbid": fbid
                })
                new_found += 1

                print(f"      ✓ {name}")

            except:
                continue

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.6)

        height = driver.execute_script("return document.body.scrollHeight")

        if height == last_height and new_found == 0:
            stable += 1
        else:
            stable = 0

        last_height = height

        if stable >= 1:
            break

    print(f"   ✔ Total friends found: {len(friends)}")
    return friends

# ─────────────────────────────────────────────
# CSV HELPERS
# ─────────────────────────────────────────────

FIELDS = [
    "source_name","source_url","source_fbid",
    "friend_name","friend_url","friend_fbid","level"
]

def append_rows(rows, file, write_header=False):
    if not rows:
        return
    with open(file,"a",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(rows)

def load_existing(file):
    net, done, edges = [], set(), set()
    if not Path(file).exists():
        return net, done, edges

    with open(file,encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            net.append(r)
            edges.add((r["source_fbid"], r["friend_fbid"]))
            if r["level"] == "2":
                done.add(normalize_profile_url(r["source_url"]))
    return net, done, edges

# ─────────────────────────────────────────────
# MAIN NETWORK SCRAPER
# ─────────────────────────────────────────────

def scrape_friends_network(driver, output="friends_network.csv", max_level=2):

    driver.get("https://www.facebook.com/me")
    time.sleep(2)

    my_url = driver.current_url
    my_name = my_url.split("/")[-1]
    my_fbid = extract_fbid_from_url(my_url)

    print("\n=== PROFILE ===")
    print(my_name, my_url)

    network, done_l2, seen_edges = load_existing(output)
    new_file = len(network) == 0

    # LEVEL 1
    print("\nLEVEL 1: Direct Friends")
    my_friends = scrape_friends_fast(driver, my_url)

    rows=[]
    for fr in my_friends:
        edge=(my_fbid,fr["fbid"])
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        rows.append({
            "source_name":my_name,
            "source_url":my_url,
            "source_fbid":my_fbid,
            "friend_name":fr["name"],
            "friend_url":fr["url"],
            "friend_fbid":fr["fbid"],
            "level":1
        })

    append_rows(rows, output, new_file)

    # LEVEL 2
    if max_level>=2:
        print("\nLEVEL 2: Friends of Friends\n")

        for i,fr in enumerate(my_friends):

            norm=normalize_profile_url(fr["url"])
            if norm in done_l2:
                continue

            print(f"[{i+1}/{len(my_friends)}] {fr['name']}")

            try:
                second = scrape_friends_fast(driver, fr["url"])
            except Exception as e:
                print("error",e)
                continue

            rows=[]
            for ff in second:
                edge=(fr["fbid"],ff["fbid"])
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                rows.append({
                    "source_name":fr["name"],
                    "source_url":fr["url"],
                    "source_fbid":fr["fbid"],
                    "friend_name":ff["name"],
                    "friend_url":ff["url"],
                    "friend_fbid":ff["fbid"],
                    "level":2
                })

            append_rows(rows, output)
            done_l2.add(norm)
            time.sleep(random.uniform(0.5,1.2))

    print("\nDONE")

# ─────────────────────────────────────────────
if __name__ == "__main__":
    from fb_login import main
    driver = main()

    if driver:
        scrape_friends_network(driver, max_level=2)
    else:
        print("Login failed")