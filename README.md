# 🍣 Sushi Shop Telegram Bot

A Telegram ordering bot for your sushi shop. Customers can browse your menu by category, add dishes to cart, and place delivery orders.

---

## 📁 Project Structure

```
sushi_bot/
├── bot.py           # Main bot logic
├── config.py        # Settings (reads from .env)
├── database.py      # MySQL connection & queries
├── keyboards.py     # Inline keyboard layouts
├── requirements.txt
└── .env.example     # Environment variables template
```

---

## ⚙️ Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create your `.env` file
```bash
cp .env.example .env
```
Then fill in your values:
- `BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
- `ADMIN_CHAT_ID` — your Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot))
- MySQL credentials

### 3. Create the database
```sql
CREATE DATABASE sushi_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
Tables are created automatically when the bot starts.

### 4. Run the bot
```bash
python bot.py
```

---

## 🗄️ Database Tables

| Table | Description |
|-------|-------------|
| `categories` | Menu categories (e.g. Rolls, Nigiri, Sets) |
| `dishes` | Dishes with name, pieces, price, category |
| `orders` | Customer orders with address & total |
| `order_items` | Individual items inside each order |

---

## ➕ Adding Menu Items (manually for now)

```sql
-- Add a category
INSERT INTO categories (name) VALUES ('Rolls');
INSERT INTO categories (name) VALUES ('Sets');

-- Add a dish
INSERT INTO dishes (category_id, name, pieces, price) 
VALUES (1, 'Philadelphia', 8, 3000);
```

> 💡 Later, the OCR module will fill this automatically from your Instagram highlights!

---

## 🔄 Coming Next
- [ ] Instaloader — download highlight images from Instagram
- [ ] OCR — extract dish name, pieces, price from images
- [ ] Auto-populate DB from OCR results
- [ ] Instagram DM auto-reply with bot link
