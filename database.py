import asyncpg
import logging
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        logger.info("Connected to PostgreSQL database.")

    async def create_tables(self):
        async with self.pool.acquire() as conn:
            # Categories table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Dishes table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS dishes (
                    id SERIAL PRIMARY KEY,
                    category_id INT NOT NULL REFERENCES categories(id),
                    name VARCHAR(200) NOT NULL,
                    pieces INT DEFAULT NULL,
                    price INT NOT NULL,
                    description TEXT DEFAULT NULL,
                    image_path VARCHAR(500) DEFAULT NULL,
                    is_available BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Orders table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(200),
                    address TEXT,
                    total INT NOT NULL,
                    status VARCHAR(20) DEFAULT 'new',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Order items table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    id SERIAL PRIMARY KEY,
                    order_id INT NOT NULL REFERENCES orders(id),
                    dish_id INT NOT NULL REFERENCES dishes(id),
                    dish_name VARCHAR(200) NOT NULL,
                    price INT NOT NULL,
                    qty INT NOT NULL
                );
            """)

        logger.info("Tables created/verified.")

    # ── Categories ──────────────────────────────────────────────────────────
    async def get_categories(self):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM categories ORDER BY id")
            return [dict(r) for r in rows]

    async def get_category_name(self, category_id: int):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT name FROM categories WHERE id = $1", category_id)
            return row["name"] if row else "Unknown"

    # ── Dishes ───────────────────────────────────────────────────────────────
    async def get_dishes_by_category(self, category_id: int):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM dishes WHERE category_id = $1 AND is_available = TRUE ORDER BY id",
                category_id
            )
            return [dict(r) for r in rows]

    async def get_dish(self, dish_id: int):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM dishes WHERE id = $1", dish_id)
            return dict(row) if row else None

    # ── Orders ───────────────────────────────────────────────────────────────
    async def create_order(self, user_id: int, username: str, cart: list, total: int, address: str) -> int:
        async with self.pool.acquire() as conn:
            order_id = await conn.fetchval(
                "INSERT INTO orders (user_id, username, address, total) VALUES ($1, $2, $3, $4) RETURNING id",
                user_id, username, address, total
            )

            for item in cart:
                await conn.execute(
                    "INSERT INTO order_items (order_id, dish_id, dish_name, price, qty) VALUES ($1, $2, $3, $4, $5)",
                    order_id, item["dish_id"], item["name"], item["price"], item["qty"]
                )

            return order_id


# Global DB instance
db = Database()
