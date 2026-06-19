import instaloader
import os
import time
import traceback
from dotenv import load_dotenv

load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME", "")
TARGET = "sushi_by_oceanfish"

print(f"instaloader version: {instaloader.__version__}")

L = instaloader.Instaloader()

print(f"Loading session for @{IG_USERNAME}...")
L.load_session_from_file(IG_USERNAME, "ig_session")
print("✅ Session loaded!")
print(f"Is logged in: {L.context.is_logged_in}")

time.sleep(5)

print(f"\nFetching profile @{TARGET}...")
try:
    profile = instaloader.Profile.from_username(L.context, TARGET)
    print(f"✅ Profile found! Name: {profile.full_name}")
except Exception as e:
    print(f"❌ Failed fetching profile: {e}")
    traceback.print_exc()
    exit()

time.sleep(5)

print(f"\nFetching highlights (skipping mediacount, going straight to highlights)...")
try:
    highlights = list(L.get_highlights(profile))
    if highlights:
        print(f"✅ Found {len(highlights)} highlights:")
        for h in highlights:
            print(f"   - '{h.title}'")
    else:
        print("⚠️ No highlights found")
except Exception as e:
    print(f"❌ Failed fetching highlights: {e}")
    traceback.print_exc()
