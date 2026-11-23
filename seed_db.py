"""Örnek e-ticaret veritabanlarını oluşturur.

Çalıştır: python seed_db.py            # ikisi de: shop.db (Türkçe) ve shop_en.db (İngilizce)
          python seed_db.py --lang en  # yalnızca biri

İki dil aynı tohumla (seed) ve aynı rastgele çekim sırasıyla üretilir: müşteri, sipariş,
tarih, adet ve durum dağılımı birebir aynıdır; yalnızca adlar, şehirler, kategoriler,
durum değerleri ve para birimi (TL / USD) farklıdır. Türkçe üretim değişmemelidir:
evals/ altındaki referans SQL'ler shop.db'deki sayılara bağlı.
"""
import argparse
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
DB_PATHS = {"tr": HERE / "shop.db", "en": HERE / "shop_en.db"}
DB_PATH = DB_PATHS["tr"]
# Örnek verinin bittiği gün. Arayüz ve değerlendirme "bugün" olarak bunu kullanır:
# gerçek tarih kullanılsaydı veri eskidikçe "geçen ay" gibi sorular boş dönerdi.
TODAY = date(2026, 11, 20)

SCHEMA_TEMPLATE = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    signup_date TEXT NOT NULL          -- YYYY-MM-DD
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL                -- {currency}
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date TEXT NOT NULL,          -- YYYY-MM-DD
    status TEXT NOT NULL               -- {statuses}
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL           -- {unit_price_note}
);
"""

# Listelerin uzunluğu ve sırası iki dilde aynı olmalı: rnd.choice aynı indeksi seçer,
# böylece Türkçe ve İngilizce veritabanı aynı dağılımı taşır.
LOCALES = {
    "tr": {
        "first": ["Ahmet", "Ayşe", "Mehmet", "Zeynep", "Can", "Elif", "Emre", "Selin", "Burak", "Deniz"],
        "last": ["Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Öztürk", "Arslan", "Koç", "Aydın", "Polat"],
        "cities": ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Konya", "Adana", "Trabzon"],
        "products": [
            ("Kablosuz Kulaklık", "Elektronik", 1499), ("Akıllı Saat", "Elektronik", 3999),
            ("Mekanik Klavye", "Elektronik", 2199), ("Powerbank", "Elektronik", 799),
            ("Koşu Ayakkabısı", "Spor", 2899), ("Yoga Matı", "Spor", 449),
            ("Dambıl Seti", "Spor", 1299), ("Kahve Makinesi", "Ev", 4599),
            ("Nevresim Takımı", "Ev", 1199), ("Masa Lambası", "Ev", 649),
            ("Roman Seti", "Kitap", 389), ("Veri Bilimi Kitabı", "Kitap", 520),
            ("Sırt Çantası", "Aksesuar", 999), ("Güneş Gözlüğü", "Aksesuar", 1750),
        ],
        # Sıra: tamamlandı, iptal, iade (ağırlıklar 88/7/5)
        "statuses": ["tamamlandi", "iptal", "iade"],
        "currency": "TL",
        "unit_price_note": "satış anındaki fiyat, TL",
    },
    "en": {
        "first": ["James", "Emma", "Liam", "Sofia", "Noah", "Mia", "Lucas", "Hannah", "Mateo", "Yuki"],
        "last": ["Smith", "Garcia", "Müller", "Rossi", "Kim", "Dubois", "Silva", "Novak", "Tanaka", "Brown"],
        "cities": ["London", "New York", "Berlin", "Paris", "Tokyo", "Toronto", "Sydney", "Madrid"],
        "products": [
            ("Wireless Headphones", "Electronics", 59.99), ("Smart Watch", "Electronics", 159.99),
            ("Mechanical Keyboard", "Electronics", 89.99), ("Power Bank", "Electronics", 29.99),
            ("Running Shoes", "Sports", 119.99), ("Yoga Mat", "Sports", 19.99),
            ("Dumbbell Set", "Sports", 49.99), ("Coffee Machine", "Home", 189.99),
            ("Bedding Set", "Home", 49.99), ("Desk Lamp", "Home", 24.99),
            ("Novel Collection", "Books", 15.99), ("Data Science Book", "Books", 21.99),
            ("Backpack", "Accessories", 39.99), ("Sunglasses", "Accessories", 69.99),
        ],
        "statuses": ["completed", "cancelled", "returned"],
        "currency": "USD",
        "unit_price_note": "price at time of sale, USD",
    },
}


def schema(lang: str) -> str:
    loc = LOCALES[lang]
    return SCHEMA_TEMPLATE.format(currency=loc["currency"], statuses=" | ".join(loc["statuses"]),
                                  unit_price_note=loc["unit_price_note"])


def build(path: Path | None = None, seed: int = 42, lang: str = "tr") -> Path:
    loc = LOCALES[lang]
    path = Path(path) if path is not None else DB_PATHS[lang]
    first, last, cities, products = loc["first"], loc["last"], loc["cities"], loc["products"]
    rnd = random.Random(seed)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(schema(lang))

    today = TODAY
    start = today - timedelta(days=540)

    customers = [
        (i, f"{rnd.choice(first)} {rnd.choice(last)}", rnd.choice(cities),
         (start + timedelta(days=rnd.randint(0, 500))).isoformat())
        for i in range(1, 201)
    ]
    con.executemany("INSERT INTO customers VALUES (?,?,?,?)", customers)
    con.executemany(
        "INSERT INTO products VALUES (?,?,?,?)",
        [(i, n, c, p) for i, (n, c, p) in enumerate(products, 1)],
    )

    item_id = 1
    for order_id in range(1, 1501):
        cust = rnd.choice(customers)
        signup = date.fromisoformat(cust[3])
        order_date = signup + timedelta(days=rnd.randint(0, (today - signup).days))
        status = rnd.choices(loc["statuses"], weights=[88, 7, 5])[0]
        con.execute("INSERT INTO orders VALUES (?,?,?,?)",
                    (order_id, cust[0], order_date.isoformat(), status))
        for pid in rnd.sample(range(1, len(products) + 1), rnd.randint(1, 3)):
            price = products[pid - 1][2] * rnd.choice([1, 1, 1, 0.9, 0.8])
            con.execute("INSERT INTO order_items VALUES (?,?,?,?,?)",
                        (item_id, order_id, pid, rnd.randint(1, 3), round(price, 2)))
            item_id += 1

    con.commit()
    con.close()
    return path


# Örnek veritabanının PostgreSQL karşılığı (testler ve run_evals.py --postgres için): aynı tablolar,
# gerçek tarih ve sayı türleri; SQLite'taki "-- açıklama" yorumları COMMENT ON COLUMN olarak.
PG_SCHEMA_TEMPLATE = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    signup_date DATE NOT NULL
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date DATE NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);
COMMENT ON COLUMN products.price IS '{currency}';
COMMENT ON COLUMN orders.status IS '{statuses}';
COMMENT ON COLUMN order_items.unit_price IS '{unit_price_note}';
"""


def copy_to_postgres(url: str, lang: str = "tr") -> None:
    """Örnek veriyi (aynı tohum, aynı satırlar) boş bir PostgreSQL veritabanına kopyalar."""
    import tempfile
    from contextlib import closing

    import psycopg

    loc = LOCALES[lang]
    with tempfile.TemporaryDirectory() as tmp:
        src = build(Path(tmp) / "shop.db", lang=lang)
        with psycopg.connect(url) as con, closing(sqlite3.connect(src)) as lite:
            con.execute(PG_SCHEMA_TEMPLATE.format(
                currency=loc["currency"], statuses=" | ".join(loc["statuses"]),
                unit_price_note=loc["unit_price_note"]))
            with con.cursor() as cur:
                for table in ("customers", "products", "orders", "order_items"):
                    rows = lite.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
                    marks = ", ".join(["%s"] * len(rows[0]))
                    cur.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Örnek veritabanlarını oluşturur.")
    parser.add_argument("--lang", choices=["tr", "en", "all"], default="all")
    args = parser.parse_args()
    for lang in (["tr", "en"] if args.lang == "all" else [args.lang]):
        print(f"Created: {build(lang=lang)}")
