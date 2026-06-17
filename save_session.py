import instaloader
import os
from dotenv import load_dotenv

load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME", "")

if not IG_USERNAME:
    print("❌ IG_USERNAME missing in .env file!")
    exit()

L = instaloader.Instaloader()

print(f"Importing Instagram session from Firefox for @{IG_USERNAME}...")
print("Make sure you are logged in to Instagram in Firefox and Firefox is CLOSED!\n")

try:
    import browser_cookie3
    cookiejar = browser_cookie3.firefox(domain_name=".instagram.com")
    L.context._session.cookies.update(cookiejar)
    L.context.username = IG_USERNAME
    L.save_session_to_file("ig_session")
    print("✅ Session saved to 'ig_session' file!")
    print("You can now run: python bot.py")
except Exception as e:
    print(f"❌ Failed: {e}")
    print("\nMake sure:")
    print("1. Firefox is installed")
    print("2. You are logged in to Instagram in Firefox")
    print("3. Firefox is completely closed before running this script")
