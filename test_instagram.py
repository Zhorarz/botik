import instaloader
import requests
import os
from dotenv import load_dotenv

load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME", "")
TARGET = "sushi_by_oceanfish"

# Load session
L = instaloader.Instaloader()
print(f"Loading session for @{IG_USERNAME}...")
L.load_session_from_file(IG_USERNAME, "ig_session")
print("✅ Session loaded!")

cookies = L.context._session.cookies.get_dict()

headers = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
    "Accept": "*/*",
    "X-IG-App-ID": "936619743392459",
    "Referer": "https://www.instagram.com/",
}

session = requests.Session()
session.cookies.update(cookies)
session.headers.update(headers)

# Get user ID
print(f"\nFetching profile @{TARGET}...")
resp = session.get(f"https://www.instagram.com/api/v1/users/web_profile_info/?username={TARGET}")
print(f"Status: {resp.status_code}")

if resp.status_code != 200:
    print(f"❌ Failed: {resp.text[:300]}")
    exit()

data = resp.json()
user_id = data["data"]["user"]["id"]
print(f"✅ User ID: {user_id}")

# Get highlights
print(f"\nFetching highlights...")
resp2 = session.get(f"https://www.instagram.com/api/v1/highlights/{user_id}/highlights_tray/")
print(f"Status: {resp2.status_code}")

if resp2.status_code != 200:
    print(f"❌ Failed: {resp2.text[:300]}")
    exit()

tray = resp2.json().get("tray", [])
if tray:
    print(f"✅ Found {len(tray)} highlights:")
    for h in tray:
        print(f"   - '{h['title']}'")
else:
    print("⚠️ No highlights found")
