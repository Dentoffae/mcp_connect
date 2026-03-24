"""
Database layer — SQLite3 product storage.
Table is created and filled with 100 test products on first run.
"""

import sqlite3
import os
from typing import Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "products.db")

# 100 test products across 7 categories
SAMPLE_PRODUCTS = [
    # Электроника (15)
    ("iPhone 15 Pro",          "Электроника", 119999.0),
    ("Samsung Galaxy S24",     "Электроника",  79999.0),
    ("MacBook Pro M3",         "Электроника", 199999.0),
    ("iPad Air 5",             "Электроника",  69999.0),
    ("AirPods Pro 2",          "Электроника",  24999.0),
    ("Sony WH-1000XM5",        "Электроника",  29999.0),
    ("Xiaomi 13T Pro",         "Электроника",  49999.0),
    ("Ноутбук HP Pavilion 15", "Электроника",  59999.0),
    ("Монитор LG 27UK850",     "Электроника",  34999.0),
    ("Клавиатура Logitech MX Keys", "Электроника", 12999.0),
    ("Мышь Logitech MX Master 3",   "Электроника",  8999.0),
    ("Веб-камера Logitech C920",     "Электроника",  7999.0),
    ("SSD Samsung 970 EVO 1TB",      "Электроника",  9999.0),
    ("Роутер TP-Link AX3000",        "Электроника",  6999.0),
    ("Умная колонка Яндекс Станция", "Электроника", 14999.0),

    # Продукты (15)
    ("Чай зелёный 100г",       "Продукты",   299.0),
    ("Чай чёрный Ахмад 200г",  "Продукты",   399.0),
    ("Кофе молотый Lavazza 500г","Продукты",  799.0),
    ("Кофе в зёрнах 1кг",      "Продукты",  1499.0),
    ("Молоко Простоквашино 1л", "Продукты",    89.0),
    ("Сыр Пармезан 200г",       "Продукты",   599.0),
    ("Хлеб ржаной бородинский", "Продукты",    79.0),
    ("Масло сливочное 200г",    "Продукты",   189.0),
    ("Яйца С1 10шт",            "Продукты",   129.0),
    ("Мёд натуральный 500г",    "Продукты",   699.0),
    ("Шоколад Lindt 90% 100г",  "Продукты",   349.0),
    ("Печенье овсяное 400г",    "Продукты",   249.0),
    ("Макароны Барилла 500г",   "Продукты",    99.0),
    ("Рис басмати 1кг",         "Продукты",   299.0),
    ("Оливковое масло Extra 500мл","Продукты",849.0),

    # Одежда (15)
    ("Футболка хлопок белая L",    "Одежда",  1299.0),
    ("Джинсы Levi's 501 синие",    "Одежда",  7999.0),
    ("Кроссовки Nike Air Max 270",  "Одежда", 12999.0),
    ("Куртка зимняя пуховая",       "Одежда", 15999.0),
    ("Свитер шерстяной серый",      "Одежда",  4999.0),
    ("Платье летнее в цветок",      "Одежда",  3499.0),
    ("Брюки деловые чёрные",        "Одежда",  5999.0),
    ("Носки хлопок 5 пар",          "Одежда",   799.0),
    ("Шапка вязаная синяя",         "Одежда",  1499.0),
    ("Перчатки кожаные чёрные",     "Одежда",  2999.0),
    ("Рубашка оксфорд белая",       "Одежда",  2499.0),
    ("Пальто осеннее бежевое",      "Одежда", 18999.0),
    ("Кеды белые Converse",         "Одежда",  4999.0),
    ("Спортивный костюм Adidas",    "Одежда",  8999.0),
    ("Бейсболка Nike чёрная",       "Одежда",  1299.0),

    # Дом и интерьер (15)
    ("Диван угловой серый",         "Дом и интерьер", 79999.0),
    ("Кресло-качалка деревянное",   "Дом и интерьер", 29999.0),
    ("Стол обеденный раздвижной",   "Дом и интерьер", 24999.0),
    ("Стул барный металлический",   "Дом и интерьер",  4999.0),
    ("Полка навесная дубовая",      "Дом и интерьер",  2999.0),
    ("Зеркало настенное овальное",  "Дом и интерьер",  5999.0),
    ("Торшер светодиодный",         "Дом и интерьер",  7999.0),
    ("Подушка декоративная 45x45",  "Дом и интерьер",  1499.0),
    ("Плед флисовый 150x200",       "Дом и интерьер",  3499.0),
    ("Картина на холсте 60x80",     "Дом и интерьер",  4999.0),
    ("Ваза стеклянная прозрачная",  "Дом и интерьер",  1999.0),
    ("Ковёр шерстяной 2x3м",        "Дом и интерьер", 12999.0),
    ("Шторы блэкаут серые 2шт",     "Дом и интерьер",  6999.0),
    ("Постельное бельё 2-спальное", "Дом и интерьер",  4999.0),
    ("Полотенце махровое 70x140",   "Дом и интерьер",  1299.0),

    # Спорт (15)
    ("Велосипед горный Stern 26",   "Спорт", 34999.0),
    ("Беговая дорожка электрическая","Спорт",49999.0),
    ("Гантели разборные 2x10кг",    "Спорт",  4999.0),
    ("Коврик для йоги TPE 6мм",     "Спорт",  2499.0),
    ("Скакалка скоростная стальная","Спорт",  1299.0),
    ("Боксёрские перчатки 12oz",    "Спорт",  3999.0),
    ("Кроссовки Nike Pegasus 41",   "Спорт",  9999.0),
    ("Бутылка для воды 1л Hydro",   "Спорт",   899.0),
    ("Спортивная сумка Adidas 30л", "Спорт",  3499.0),
    ("Турник дверной усиленный",    "Спорт",  2999.0),
    ("Теннисная ракетка Wilson Pro","Спорт",  5999.0),
    ("Мяч футбольный Nike Strike",  "Спорт",  2999.0),
    ("Велошлем Author 54-58",       "Спорт",  4999.0),
    ("Эспандер резиновый 3 шт",     "Спорт",   799.0),
    ("Фитнес-браслет Xiaomi Band 8","Спорт",  4999.0),

    # Книги (10)
    ("Мастер и Маргарита Булгаков", "Книги",   599.0),
    ("Война и мир Толстой",         "Книги",   799.0),
    ("Атлант расправил плечи Рэнд", "Книги",  1299.0),
    ("Гарри Поттер комплект 7 книг","Книги",  3999.0),
    ("Преступление и наказание",    "Книги",   499.0),
    ("Маленький принц Экзюпери",    "Книги",   399.0),
    ("Python для всех Северанс",    "Книги",  1499.0),
    ("Чистый код Мартин",           "Книги",  1799.0),
    ("Богатый папа Бедный папа",    "Книги",   699.0),
    ("Думай медленно решай быстро", "Книги",   849.0),

    # Красота (15)
    ("Шампунь Pantene Pro-V 400мл", "Красота",   599.0),
    ("Крем для лица Nivea дневной", "Красота",   799.0),
    ("Духи Chanel No5 50мл EDP",    "Красота", 12999.0),
    ("Тушь Maybelline Lash Sensational","Красота",799.0),
    ("Зубная паста Colgate 150г",   "Красота",   199.0),
    ("Бритва Gillette Fusion 5",    "Красота",  1299.0),
    ("Гель для душа L'Occitane",    "Красота",  1499.0),
    ("Маска для лица глиняная",     "Красота",   699.0),
    ("Сыворотка витамин C 30мл",    "Красота",  2499.0),
    ("Набор кистей 12шт для макияжа","Красота", 1999.0),
    ("Крем для рук Neutrogena",     "Красота",   449.0),
    ("Лак для ногтей OPI красный",  "Красота",   899.0),
    ("Мицеллярная вода Bioderma",   "Красота",   999.0),
    ("Солнцезащитный крем SPF50",   "Красота",  1499.0),
    ("Помада стойкая Dior Rouge",   "Красота",  3999.0),
]


def _ulower(s: str) -> str:
    """Unicode-aware lowercase for SQLite — handles Cyrillic and other non-ASCII."""
    return s.lower() if s else ""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Register Python's str.lower() so SQLite can use it for Cyrillic
    conn.create_function("ULOWER", 1, _ulower)
    return conn


def init_db() -> None:
    """Create table and seed 100 test products if empty."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL,
            category TEXT    NOT NULL,
            price    REAL    NOT NULL
        )
    """)
    conn.commit()

    count = cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count == 0:
        cursor.executemany(
            "INSERT INTO products (name, category, price) VALUES (?, ?, ?)",
            SAMPLE_PRODUCTS,
        )
        conn.commit()
        print(f"[DB] Seeded {len(SAMPLE_PRODUCTS)} test products into products.db")
    else:
        print(f"[DB] products.db ready ({count} products)")

    conn.close()


def get_all_products(limit: int = 50, offset: int = 0) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, category, price FROM products LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_products_by_name(name: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, category, price FROM products WHERE ULOWER(name) LIKE ULOWER(?)",
        (f"%{name}%",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product_by_id(product_id: int) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, name, category, price FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def find_similar_products(product_id: int) -> Dict:
    """Return all products in the same category as product_id, excluding itself."""
    conn = get_connection()
    source = conn.execute(
        "SELECT id, name, category, price FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    if not source:
        conn.close()
        return {"source": None, "products": [], "count": 0}
    source_dict = dict(source)
    rows = conn.execute(
        "SELECT id, name, category, price FROM products WHERE ULOWER(category) = ULOWER(?) AND id != ?",
        (source_dict["category"], product_id),
    ).fetchall()
    conn.close()
    products = [dict(r) for r in rows]
    return {"source": source_dict, "products": products, "count": len(products)}


def search_products_by_category(category: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, category, price FROM products WHERE ULOWER(category) LIKE ULOWER(?)",
        (f"%{category}%",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_product_to_db(name: str, category: str, price: float) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, category, price) VALUES (?, ?, ?)",
        (name, category, price),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id
