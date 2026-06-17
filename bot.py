import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_CHAT_ID
from database import db
from keyboards import main_menu_kb, category_kb, dish_kb, order_kb, confirm_order_kb, admin_menu_kb
from instagram_importer import download_highlights, extract_text_from_image, parse_dish, save_to_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ─── States ───────────────────────────────────────────────────────────────────
class OrderState(StatesGroup):
    browsing = State()
    adding_to_cart = State()
    confirming = State()
    entering_address = State()

class ImportState(StatesGroup):
    waiting_username = State()
    waiting_highlight = State()


# ─── /start ───────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(cart=[])

    # If admin — show admin menu too
    if message.from_user.id == ADMIN_CHAT_ID:
        await message.answer(
            f"👑 Welcome Admin!\n\nWhat would you like to do?",
            reply_markup=admin_menu_kb()
        )
    else:
        await message.answer(
            f"🍣 Welcome to our Sushi Shop!\n\n"
            f"Browse our menu and place your order right here.\n"
            f"Use the buttons below to get started:",
            reply_markup=main_menu_kb()
        )


# ─── Admin: Import Menu from Instagram ───────────────────────────────────────
@dp.callback_query(F.data == "import_menu")
async def import_menu_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("❌ Not authorized.", show_alert=True)
        return
    await state.set_state(ImportState.waiting_username)
    await callback.message.edit_text(
        "📸 *Import Menu from Instagram*\n\n"
        "Send me the Instagram username\n"
        "Example: `sushi_shop_yerevan`",
        parse_mode="Markdown"
    )
    await callback.answer()


@dp.message(ImportState.waiting_username)
async def import_receive_username(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    await state.update_data(instagram_username=username)
    await state.set_state(ImportState.waiting_highlight)
    await message.answer(
        f"✅ Username: *@{username}*\n\n"
        f"Now send me the highlight name to import\n"
        f"Example: `Menu` or `Rolls`\n\n"
        f"_(it must match exactly the highlight title on Instagram)_",
        parse_mode="Markdown"
    )


@dp.message(ImportState.waiting_highlight)
async def import_receive_highlight(message: Message, state: FSMContext):
    highlight_name = message.text.strip()
    data = await state.get_data()
    username = data.get("instagram_username")

    await state.clear()

    status_msg = await message.answer(
        f"⏳ Starting import...\n\n"
        f"📸 Instagram: *@{username}*\n"
        f"🔖 Highlight: *{highlight_name}*\n\n"
        f"This may take a minute...",
        parse_mode="Markdown"
    )

    try:
        # Run in executor so it doesn't block the bot
        loop = asyncio.get_event_loop()
        downloaded = await loop.run_in_executor(
            None, download_highlights, username, highlight_name
        )

        if not downloaded:
            await status_msg.edit_text(
                f"❌ No images found!\n\n"
                f"Make sure:\n"
                f"• The username *@{username}* is correct\n"
                f"• The highlight *'{highlight_name}'* exists and is public",
                parse_mode="Markdown"
            )
            return

        await status_msg.edit_text(
            f"📥 Downloaded *{len(downloaded)}* images\n"
            f"🔍 Running OCR...",
            parse_mode="Markdown"
        )

        # OCR + parse
        dishes_by_category = {}
        failed = 0
        for item in downloaded:
            text = extract_text_from_image(item["path"])
            dish = parse_dish(text)
            if dish:
                dishes_by_category.setdefault(item["category"], []).append(dish)
            else:
                failed += 1

        total_dishes = sum(len(v) for v in dishes_by_category.values())

        if not total_dishes:
            await status_msg.edit_text(
                f"⚠️ Downloaded {len(downloaded)} images but couldn't parse any dishes.\n\n"
                f"The OCR may not be reading your image style correctly.\n"
                f"Send me a sample image and I can help tune it!",
                parse_mode="Markdown"
            )
            return

        # Save to DB
        await save_to_db(dishes_by_category)

        lines = []
        for cat, dishes in dishes_by_category.items():
            lines.append(f"*{cat}*: {len(dishes)} dishes")

        await status_msg.edit_text(
            f"✅ *Import complete!*\n\n"
            f"📦 {total_dishes} dishes saved to menu\n"
            + "\n".join(lines) +
            (f"\n⚠️ {failed} images skipped (couldn't parse)" if failed else ""),
            reply_markup=admin_menu_kb(),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Import failed: {e}")
        await status_msg.edit_text(
            f"❌ Import failed: `{str(e)}`\n\nCheck the username and try again.",
            parse_mode="Markdown"
        )


# ─── Show Categories ──────────────────────────────────────────────────────────
@dp.callback_query(F.data == "menu")
async def show_categories(callback: CallbackQuery):
    categories = await db.get_categories()
    if not categories:
        await callback.message.edit_text("😔 Menu is currently unavailable. Please try again later.")
        return
    await callback.message.edit_text(
        "📋 Choose a category:",
        reply_markup=category_kb(categories)
    )
    await callback.answer()


# ─── Show Dishes by Category ──────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("category_"))
async def show_dishes(callback: CallbackQuery):
    category_id = int(callback.data.split("_")[1])
    dishes = await db.get_dishes_by_category(category_id)
    category_name = await db.get_category_name(category_id)

    if not dishes:
        await callback.answer("No dishes in this category yet.", show_alert=True)
        return

    await callback.message.edit_text(
        f"🍱 *{category_name}*\n\nChoose a dish:",
        reply_markup=dish_kb(dishes, category_id),
        parse_mode="Markdown"
    )
    await callback.answer()


# ─── Show Dish Detail ─────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("dish_"))
async def show_dish(callback: CallbackQuery, state: FSMContext):
    dish_id = int(callback.data.split("_")[1])
    dish = await db.get_dish(dish_id)

    if not dish:
        await callback.answer("Dish not found.", show_alert=True)
        return

    text = (
        f"🍣 *{dish['name']}*\n\n"
        f"📦 Pieces: {dish['pieces']}\n"
        f"💰 Price: {dish['price']} AMD\n"
    )
    if dish.get('description'):
        text += f"\n📝 {dish['description']}"

    await callback.message.edit_text(
        text,
        reply_markup=order_kb(dish_id, dish['category_id']),
        parse_mode="Markdown"
    )
    await callback.answer()


# ─── Add to Cart ──────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("add_"))
async def add_to_cart(callback: CallbackQuery, state: FSMContext):
    dish_id = int(callback.data.split("_")[1])
    dish = await db.get_dish(dish_id)

    data = await state.get_data()
    cart = data.get("cart", [])

    # Check if already in cart, increase qty
    for item in cart:
        if item["dish_id"] == dish_id:
            item["qty"] += 1
            await state.update_data(cart=cart)
            await callback.answer(f"✅ {dish['name']} x{item['qty']} in cart", show_alert=False)
            return

    cart.append({
        "dish_id": dish_id,
        "name": dish["name"],
        "price": dish["price"],
        "qty": 1
    })
    await state.update_data(cart=cart)
    await callback.answer(f"✅ {dish['name']} added to cart!", show_alert=False)


# ─── View Cart ────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "cart")
async def view_cart(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", [])

    if not cart:
        await callback.answer("🛒 Your cart is empty!", show_alert=True)
        return

    total = sum(item["price"] * item["qty"] for item in cart)
    lines = [f"• {item['name']} x{item['qty']} — {item['price'] * item['qty']} AMD" for item in cart]
    text = "🛒 *Your Cart:*\n\n" + "\n".join(lines) + f"\n\n💰 *Total: {total} AMD*"

    await callback.message.edit_text(
        text,
        reply_markup=confirm_order_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()


# ─── Clear Cart ───────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery, state: FSMContext):
    await state.update_data(cart=[])
    await callback.message.edit_text(
        "🗑 Cart cleared!\n\nUse the menu below to start over:",
        reply_markup=main_menu_kb()
    )
    await callback.answer()


# ─── Confirm Order → Ask for address ─────────────────────────────────────────
@dp.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OrderState.entering_address)
    await callback.message.edit_text(
        "📍 Please send your delivery address (or type *Pickup* if you'll collect):",
        parse_mode="Markdown"
    )
    await callback.answer()


# ─── Receive Address & Place Order ───────────────────────────────────────────
@dp.message(OrderState.entering_address)
async def receive_address(message: Message, state: FSMContext):
    address = message.text
    data = await state.get_data()
    cart = data.get("cart", [])

    if not cart:
        await message.answer("Your cart is empty. Start over with /start")
        await state.clear()
        return

    total = sum(item["price"] * item["qty"] for item in cart)
    user = message.from_user

    # Save order to DB
    order_id = await db.create_order(
        user_id=user.id,
        username=user.username or user.first_name,
        cart=cart,
        total=total,
        address=address
    )

    # Notify admin
    lines = [f"• {item['name']} x{item['qty']} — {item['price'] * item['qty']} AMD" for item in cart]
    admin_text = (
        f"🆕 *New Order #{order_id}*\n\n"
        f"👤 Customer: @{user.username or user.first_name} (ID: {user.id})\n"
        f"📍 Address: {address}\n\n"
        f"🛒 Items:\n" + "\n".join(lines) +
        f"\n\n💰 Total: {total} AMD"
    )
    try:
        await bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

    # Confirm to user
    await message.answer(
        f"✅ *Order #{order_id} placed successfully!*\n\n"
        f"We'll prepare your order and deliver to:\n📍 {address}\n\n"
        f"Total: *{total} AMD*\n\nThank you! 🍣",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown"
    )
    await state.clear()
    await state.update_data(cart=[])


# ─── Back to Main Menu ────────────────────────────────────────────────────────
@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🍣 Main Menu — what would you like to do?",
        reply_markup=main_menu_kb()
    )
    await callback.answer()


# ─── Run ──────────────────────────────────────────────────────────────────────
async def main():
    await db.connect()
    await db.create_tables()
    logger.info("Bot started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
