import pytesseract
from PIL import Image
import asyncpg
import re
import logging
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

# ── Tesseract path (Windows) ──────────────────────────────────────────────────
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

logger = logging.getLogger(__name__)


# ── OCR — extract text from image ────────────────────────────────────────────
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


# ── Parse OCR text → dish info ───────────────────────────────────────────────
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

    price_pattern = re.compile(r'(\d{3,6})\s*(?:amd|AMD|֏)?', re.IGNORECASE)
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


# ── Save dishes to PostgreSQL ────────────────────────────────────────────────
async def save_dishes_to_db(category_name: str, dishes: list) -> int:
    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

    saved = 0
    try:
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
            exists = await conn.fetchrow(
                "SELECT id FROM dishes WHERE name = $1 AND category_id = $2",
                dish["name"], category_id
            )
            if exists:
                logger.info(f"Skipping duplicate: {dish['name']}")
                continue

            await conn.execute(
                """INSERT INTO dishes (category_id, name, pieces, price)
                   VALUES ($1, $2, $3, $4)""",
                category_id, dish["name"], dish.get("pieces"), dish["price"]
            )
            saved += 1
            logger.info(f"Saved dish: {dish['name']} | {dish.get('pieces')} pcs | {dish['price']} AMD")

    finally:
        await conn.close()

    return saved
