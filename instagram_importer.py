import instaloader
import pytesseract
from PIL import Image
import asyncpg
import asyncio
import os
import re
import time
import logging
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, IG_USERNAME

# ── Tesseract path (Windows) ──────────────────────────────────────────────────
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "highlights"


# ── Step 1: Download highlight images using instaloader's native downloader ──
def download_highlights(instagram_username: str, highlight_filter: str = None):
    logger.info(f"Connecting to Instagram for @{instagram_username}...")

    L = instaloader.Instaloader(
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
        # Slow things down so Instagram doesn't flag us
        max_connection_attempts=3,
        request_timeout=30,
    )

    session_file = "ig_session"
    if not os.path.exists(session_file):
        raise Exception("Session file 'ig_session' not found! Run save_session.py first.")

    L.load_session_from_file(IG_USERNAME, session_file)
    logger.info(f"Loaded Instagram session for @{IG_USERNAME}")

    # Be gentle - wait before making requests
    time.sleep(3)

    profile = instaloader.Profile.from_username(L.context, instagram_username)
    logger.info(f"Profile found: {profile.full_name}")

    time.sleep(3)

    downloaded = []
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    highlights = L.get_highlights(profile)

    found_any = False
    for highlight in highlights:
        found_any = True

        if highlight_filter and highlight.title.lower() != highlight_filter.lower():
            logger.info(f"Skipping highlight: {highlight.title}")
            continue

        highlight_dir = os.path.join(DOWNLOAD_DIR, highlight.title)
        os.makedirs(highlight_dir, exist_ok=True)
        logger.info(f"Downloading highlight: {highlight.title}")

        for item in highlight.get_items():
            if item.is_video:
                continue

            filename_base = os.path.join(highlight_dir, f"{item.mediaid}")

            # Use instaloader's built-in download method (handles retries/throttling)
            L.download_pic(filename_base, item.url, item.date_utc)

            actual_file = f"{filename_base}.jpg"
            if os.path.exists(actual_file):
                downloaded.append({"path": actual_file, "category": highlight.title})
                logger.info(f"  Downloaded: {actual_file}")

            time.sleep(1.5)  # gentle pacing between image downloads

        time.sleep(2)  # pacing between highlights

    if not found_any:
        raise Exception("No highlights found on this account (or account requires follow).")

    logger.info(f"Total images downloaded: {len(downloaded)}")
    return downloaded


# ── Step 2: OCR — extract text from image ────────────────────────────────────
def extract_text_from_image(image_path: str) -> str:
    try:
        img = Image.open(image_path)
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
        img = img.convert("L")
        # hye = Armenian, eng = English (numbers, AMD, pcs) — both needed
        text = pytesseract.image_to_string(img, lang="hye+eng")
        return text.strip()
    except Exception as e:
        logger.error(f"OCR failed for {image_path}: {e}")
        return ""


# ── Step 3: Parse OCR text → dish info ───────────────────────────────────────
def parse_dish(text: str) -> dict | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    dish_name = None
    pieces = None
    price = None

    price_pattern = re.compile(r'(\d{3,6})\s*(?:amd|AMD|֏)?', re.IGNORECASE)
    pieces_pattern = re.compile(r'(\d+)\s*(?:pcs|pc|pieces|կտ)', re.IGNORECASE)

    full_text = " ".join(lines)

    price_match = price_pattern.search(full_text)
    if price_match:
        price = int(price_match.group(1))

    pieces_match = pieces_pattern.search(full_text)
    if pieces_match:
        pieces = int(pieces_match.group(1))

    for line in lines:
        if not re.match(r'^[\d\s,.*AMD֏pcs]+$', line, re.IGNORECASE):
            dish_name = line.strip()
            break

    if not dish_name or not price:
        logger.warning(f"Could not parse dish from text:\n{text}")
        return None

    return {"name": dish_name, "pieces": pieces, "price": price}


# ── Step 4: Save to PostgreSQL ────────────────────────────────────────────────
async def save_to_db(dishes_by_category: dict):
    conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    try:
        for category_name, dishes in dishes_by_category.items():
            if not dishes:
                continue

            row = await conn.fetchrow("SELECT id FROM categories WHERE name = $1", category_name)
            if row:
                category_id = row["id"]
            else:
                category_id = await conn.fetchval(
                    "INSERT INTO categories (name) VALUES ($1) RETURNING id", category_name
                )
                logger.info(f"Created category: {category_name} (id={category_id})")

            for dish in dishes:
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
