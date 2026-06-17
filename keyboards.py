from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍣 View Menu", callback_data="menu")],
        [InlineKeyboardButton(text="🛒 My Cart", callback_data="cart")],
    ])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍣 View Menu", callback_data="menu")],
        [InlineKeyboardButton(text="🛒 My Cart", callback_data="cart")],
        [InlineKeyboardButton(text="📸 Import Menu from Instagram", callback_data="import_menu")],
    ])


def category_kb(categories: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"🍱 {cat['name']}", callback_data=f"category_{cat['id']}")]
        for cat in categories
    ]
    buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def dish_kb(dishes: list, category_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"{dish['name']} — {dish['price']} AMD",
            callback_data=f"dish_{dish['id']}"
        )]
        for dish in dishes
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="menu")])
    buttons.append([InlineKeyboardButton(text="🛒 My Cart", callback_data="cart")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_kb(dish_id: int, category_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add to Cart", callback_data=f"add_{dish_id}")],
        [InlineKeyboardButton(text="⬅️ Back to Category", callback_data=f"category_{category_id}")],
        [InlineKeyboardButton(text="🛒 My Cart", callback_data="cart")],
    ])


def confirm_order_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Place Order", callback_data="confirm_order")],
        [InlineKeyboardButton(text="🗑 Clear Cart", callback_data="clear_cart")],
        [InlineKeyboardButton(text="🍣 Continue Shopping", callback_data="menu")],
    ])
