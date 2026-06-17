import instaloader
import pytesseract
import requests
from PIL import Image
import asyncpg
import asyncio
import os
import re
import json
import logging
from io import BytesIO
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, IG_USERNAME

# ── Tesseract path (Windows) ──────────────────────────────────────────────────
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "highlights"


# ── Load session cookies from instaloader session file ────────────────────────
def get_session_cookies() -> dict:
    L = instaloader.Instaloader()
    L.load_session_from_file(IG_USERNAME, "ig_session")
    cookies = L.context._session.cookies.get_dict()
    return cookies


# ── Step 1: Download highlight images via Instagram mobile API ────────────────
def download_highlights(instagram_username: str, highlight_filter: str = None):
    logger.info(f"Fetching highlights for @{instagram_username}...")

    cookies = get_session_cookies()

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": "936619743392459",
        "X-ASBD-ID": "198387",
        "Referer": "https://www.instagram.com/",
    }

    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(headers)

    # Get user ID first
    resp = session.get(f"https://www.instagram.com/api/v1/users/web_profile_info/?username={instagram_username}")
    if resp.status_code != 200:
        raise Exception(f"Could not fetch profile: {resp.status_code} {resp.text[:200]}")

    data = resp.json()
    user_id = data["data"]["user"]["id"]
    logger.info(f"User ID: {user_id}")

    # Get highlights reel
    resp2 = session.get(
        f"https://www.instagram.com/api/v1/highlights/{user_id}/highlights_tray/"
    )
    if resp2.status_code != 200:
        raise Exception(f"Could not fetch highlights tray: {resp2.status_code} {resp2.text[:200]}")

    tray = resp2.json().get("tray", [])
    if not tray:
        raise Exception("No highlights found on this account.")

    logger.info(f"Found {len(tray)} highlights")

    downloaded = []
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    for reel in tray:
        title = reel.get("title", "Highlight")

        if highlight_filter and title.lower() != highlight_filter.lower():
            logger.info(f"Skipping highlight: {title}")
            continue

        logger.info(f"Processing highlight: {title}")

        # Get full highlight items
        reel_id = reel["id"]
        resp3 = session.get(
            f"https://www.instagram.com/api/v1/feed/reels_media/?reel_ids={reel_id}"
        )
        if resp3.status_code != 200:
            logger.warning(f"Could not fetch items for '{title}': {resp3.status_code}")
            continue

        reel_data = resp3.json()
        reels = reel_data.get("reels", {})
        reel_info = reels.get(str(reel_id), {})
        items = reel_info.get("items", [])

        highlight_dir = os.path.join(DOWNLOAD_DIR, title)
        os.makedirs(highlight_dir, exist_ok=True)

        for item in items:
            # Skip videos
            if item.get("media_type") == 2:
                continue

            # Get best image URL
            candidates = item.get("image_versions2", {}).get("candidates", [])
            if not candidates:
                continue

            img_url = candidates[0]["url"]
            media_id = item.get("pk", item.get("id", "unknown"))
            filename = os.path.join(highlight_dir, f"{media_id}.jpg")

            img_resp = session.get(img_url)
            if img_resp.status_code == 200:
                with open(filename, "wb") as f:
                    f.write(img_resp.content)
                downloaded.append({"path": filename, "category": title})
                logger.info(f"  Downloaded: {filename}")

    logger.info(f"Total images downloaded: {len(downloaded)}")
    return downloaded

    downloaded = []
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    for highlight in highlights:
        # Filter by highlight name if provided
        if highlight_filter and highlight.title.lower() != highlight_filter.lower():
            logger.info(f"Skipping highlight: {highlight.title}")
            continue

        highlight_dir = os.path.join(DOWNLOAD_DIR, highlight.title)
        os.makedirs(highlight_dir, exist_ok=True)
        logger.info(f"Downloading highlight: {highlight.title}")

        for item in highlight.get_items():
            if item.is_video:
                continue  # skip videos, images only
            filename = os.path.join(highlight_dir, f"{item.mediaid}.jpg")
            L.download_pic(filename, item.url, item.date_utc)
            downloaded.append({
                "path": filename,
                "category": highlight.title
            })
            logger.info(f"  Downloaded: {filename}")

    logger.info(f"Total images downloaded: {len(downloaded)}")
    return downloaded


# ── Step 2: OCR — extract text from image ────────────────────────────────────
def extract_text_from_image(image_path: str) -> str:
    try:
        img = Image.open(image_path)
        # Upscale for better OCR accuracy
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
        # Convert to grayscale
        img = img.convert("L")
        text = pytesseract.image_to_string(img, lang="eng")
        return text.strip()
    except Exception as e:
        logger.error(f"OCR failed for {image_path}: {e}")
        return ""


# ── Step 3: Parse OCR text → dish info ───────────────────────────────────────
def parse_dish(text: str) -> dict | None:
    """
    Tries to extract dish name, pieces, and price from OCR text.
    
    Expects formats like:
      Philadelphia 8pcs 3000AMD
      California Roll 8 pcs 2500 AMD
      Dragon Roll 3500
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    dish_name = None
    pieces = None
    price = None

    # Look for price — number followed by AMD or just a standalone large number
    price_pattern = re.compile(r'(\d{3,6})\s*(?:amd|AMD|֏)?', re.IGNORECASE)
    # Look for pieces — number followed by pcs/pc/pieces
    pieces_pattern = re.compile(r'(\d+)\s*(?:pcs|pc|pieces|կտ)', re.IGNORECASE)

    full_text = " ".join(lines)

    price_match = price_pattern.search(full_text)
    if price_match:
        price = int(price_match.group(1))

    pieces_match = pieces_pattern.search(full_text)
    if pieces_match:
        pieces = int(pieces_match.group(1))

    # Dish name = first meaningful line (not just numbers)
    for line in lines:
        if not re.match(r'^[\d\s,.*AMD֏pcs]+$', line, re.IGNORECASE):
            dish_name = line.strip()
            break

    if not dish_name or not price:
        logger.warning(f"Could not parse dish from text:\n{text}")
        return None

    return {
        "name": dish_name,
        "pieces": pieces,
        "price": price
    }


# ── Step 4: Save to PostgreSQL ────────────────────────────────────────────────
async def save_to_db(dishes_by_category: dict):
    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

    try:
        for category_name, dishes in dishes_by_category.items():
            if not dishes:
                continue

            # Get or create category
            row = await conn.fetchrow(
                "SELECT id FROM categories WHERE name = $1", category_name
            )
            if row:
                category_id = row["id"]
            else:
                category_id = await conn.fetchval(
                    "INSERT INTO categories (name) VALUES ($1) RETURNING id",
                    category_name
                )
                logger.info(f"Created category: {category_name} (id={category_id})")

            for dish in dishes:
                # Skip if dish with same name already exists
                exists = await conn.fetchrow(
                    "SELECT id FROM dishes WHERE name = $1 AND category_id = $2",
                    dish["name"], category_id
                )
                if exists:
                    logger.info(f"  Skipping duplicate: {dish['name']}")
                    continue

                await conn.execute(
                    """INSERT INTO dishes (category_id, name, pieces, price)
                       VALUES ($1, $2, $3, $4)""",
                    category_id, dish["name"], dish.get("pieces"), dish["price"]
                )
                logger.info(f"  Saved dish: {dish['name']} | {dish.get('pieces')} pcs | {dish['price']} AMD")

    finally:
        await conn.close()


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    # ← Put your Instagram username here
    INSTAGRAM_USERNAME = "your_instagram_username"

    # Step 1: Download
    downloaded = download_highlights(INSTAGRAM_USERNAME)

    if not downloaded:
        logger.warning("No images downloaded. Check the Instagram username.")
        return

    # Step 2 & 3: OCR + Parse
    dishes_by_category = {}

    for item in downloaded:
        category = item["category"]
        image_path = item["path"]

        text = extract_text_from_image(image_path)
        logger.info(f"OCR result for {image_path}:\n{text}\n---")

        dish = parse_dish(text)
        if dish:
            dishes_by_category.setdefault(category, []).append(dish)

    # Step 4: Save to DB
    if dishes_by_category:
        await save_to_db(dishes_by_category)
        total = sum(len(v) for v in dishes_by_category.values())
        logger.info(f"\n✅ Done! {total} dishes saved to database.")
    else:
        logger.warning("No dishes could be parsed from images. Check OCR results above.")


if __name__ == "__main__":
    asyncio.run(main())
