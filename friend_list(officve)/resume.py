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



def wait_until_facebook_ready(driver, timeout=120):
    """
    Wait until Facebook login is fully active and homepage is ready.
    """

    print("\n⏳ Waiting for Facebook session to become ready...")

    end = time.time() + timeout

    while time.time() < end:
        try:
            current_url = driver.current_url.lower()
        except:
            current_url = ""

        # detect cookies
        try:
            cookies = [c['name'] for c in driver.get_cookies()]
        except:
            cookies = []

        # SUCCESS CONDITIONS
        if ("c_user" in cookies or "xs" in cookies) and \
           "login" not in current_url and \
           "checkpoint" not in current_url:

            print("✅ Facebook session confirmed")
            return True

        # homepage redirect detection
        if "facebook.com" in current_url and \
           "login" not in current_url and \
           "checkpoint" not in current_url:
            print("✅ Facebook homepage detected")
            return True

        time.sleep(2)

    print("❌ Facebook session not confirmed in time")
    return False

def scrape_from_csv(driver, input_csv, output_csv):
    import csv
    from pathlib import Path

    print("\nReading source CSV...")

    seen_edges = set()
    write_header = not Path(output_csv).exists()

    with open(input_csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, 1):
            friend_url = row["friend_url"]
            friend_name = row["friend_name"]
            friend_fbid = row["friend_fbid"]

            if not friend_url:
                continue

            print(f"\n[{i}] Scraping friends of: {friend_name}")

            try:
                friends = scrape_friends_fast(driver, friend_url)
            except Exception as e:
                print("   error:", e)
                continue

            rows_to_write = []

            for fr in friends:
                edge = (friend_fbid, fr["fbid"])
                if edge in seen_edges:
                    continue

                seen_edges.add(edge)

                rows_to_write.append({
                    "source_name": friend_name,
                    "source_url": friend_url,
                    "source_fbid": friend_fbid,
                    "friend_name": fr["name"],
                    "friend_url": fr["url"],
                    "friend_fbid": fr["fbid"],
                    "level": 2
                })

            append_rows(rows_to_write, output_csv, write_header)
            write_header = False

            time.sleep(random.uniform(0.8, 1.8))

    print("\nFinished scraping from CSV.")
    

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
    network = []
    done_l2 = set()
    seen_edges = set()
    last_source = None

    if not Path(file).exists():
        return network, done_l2, seen_edges, last_source

    with open(file, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            network.append(r)
            seen_edges.add((r["source_fbid"], r["friend_fbid"]))

            # mark completed level 2 sources
            if r["level"] == "2":
                done_l2.add(normalize_profile_url(r["source_url"]))
                last_source = normalize_profile_url(r["source_url"])

    return network, done_l2, seen_edges, last_source

# ─────────────────────────────────────────────
# MAIN NETWORK SCRAPER
# ─────────────────────────────────────────────

def scrape_friends_network(driver, output, max_level=2):

    driver.get("https://www.facebook.com/me")
    time.sleep(2)

    my_url = driver.current_url
    my_name = my_url.split("/")[-1]
    my_fbid = extract_fbid_from_url(my_url)

    print("\n=== PROFILE ===")
    print(my_name, my_url)

    network, done_l2, seen_edges, last_source = load_existing(output)
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
    if max_level >= 2:
        print("\nLEVEL 2: Friends of Friends\n")

        resume = last_source is None

        for i, fr in enumerate(my_friends):

            norm = normalize_profile_url(fr["url"])

            # resume from next friend after last processed
            if not resume:
                if norm == last_source:
                    resume = True
                continue

            if norm in done_l2:
                continue

            print(f"[{i+1}/{len(my_friends)}] {fr['name']}")

            try:
                second = scrape_friends_fast(driver, fr["url"])
            except Exception as e:
                print("error", e)
                continue

            rows = []
            for ff in second:
                edge = (fr["fbid"], ff["fbid"])
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                rows.append({
                    "source_name": fr["name"],
                    "source_url": fr["url"],
                    "source_fbid": fr["fbid"],
                    "friend_name": ff["name"],
                    "friend_url": ff["url"],
                    "friend_fbid": ff["fbid"],
                    "level": 2
                })

            append_rows(rows, output)
            done_l2.add(norm)
            time.sleep(random.uniform(0.6, 1.4))

    print("\nDONE")

# ─────────────────────────────────────────────
if __name__ == "__main__":
    from fb_login import main
    import time

    driver = main()

    if driver:
        print("\n🚀 Starting scraping immediately...\n")

        scrape_from_csv(
            driver,
            input_csv=r"C:\Users\vibhor\Desktop\haya\Book1.csv",
            output_csv=r"C:\Users\vibhor\Desktop\haya\haya22_Book1_friends_expanded.csv"
        )
    else:
        print("Driver not started")