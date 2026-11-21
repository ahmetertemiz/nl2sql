"""Örnek e-ticaret veritabanını (shop.db) oluşturur. Çalıştır: python seed_db.py"""
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "shop.db"

SCHEMA = """
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
    price REAL NOT NULL                -- TL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date TEXT NOT NULL,          -- YYYY-MM-DD
    status TEXT NOT NULL               -- tamamlandi | iptal | iade
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL           -- satış anındaki fiyat, TL
);
"""

FIRST = ["Ahmet", "Ayşe", "Mehmet", "Zeynep", "Can", "Elif", "Emre", "Selin", "Burak", "Deniz"]
LAST = ["Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Öztürk", "Arslan", "Koç", "Aydın", "Polat"]
CITIES = ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Konya", "Adana", "Trabzon"]
PRODUCTS = [
    ("Kablosuz Kulaklık", "Elektronik", 1499), ("Akıllı Saat", "Elektronik", 3999),
    ("Mekanik Klavye", "Elektronik", 2199), ("Powerbank", "Elektronik", 799),
    ("Koşu Ayakkabısı", "Spor", 2899), ("Yoga Matı", "Spor", 449),
    ("Dambıl Seti", "Spor", 1299), ("Kahve Makinesi", "Ev", 4599),
    ("Nevresim Takımı", "Ev", 1199), ("Masa Lambası", "Ev", 649),
    ("Roman Seti", "Kitap", 389), ("Veri Bilimi Kitabı", "Kitap", 520),
    ("Sırt Çantası", "Aksesuar", 999), ("Güneş Gözlüğü", "Aksesuar", 1750),
]


def build(path: Path = DB_PATH, seed: int = 42) -> Path:
    rnd = random.Random(seed)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)

    today = date(2026, 11, 20)
    start = today - timedelta(days=540)

    customers = [
        (i, f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", rnd.choice(CITIES),
         (start + timedelta(days=rnd.randint(0, 500))).isoformat())
        for i in range(1, 201)
    ]
    con.executemany("INSERT INTO customers VALUES (?,?,?,?)", customers)
    con.executemany(
        "INSERT INTO products VALUES (?,?,?,?)",
        [(i, n, c, p) for i, (n, c, p) in enumerate(PRODUCTS, 1)],
    )

    item_id = 1
    for order_id in range(1, 1501):
        cust = rnd.choice(customers)
        signup = date.fromisoformat(cust[3])
        order_date = signup + timedelta(days=rnd.randint(0, (today - signup).days))
        status = rnd.choices(["tamamlandi", "iptal", "iade"], weights=[88, 7, 5])[0]
        con.execute("INSERT INTO orders VALUES (?,?,?,?)",
                    (order_id, cust[0], order_date.isoformat(), status))
        for pid in rnd.sample(range(1, len(PRODUCTS) + 1), rnd.randint(1, 3)):
            price = PRODUCTS[pid - 1][2] * rnd.choice([1, 1, 1, 0.9, 0.8])
            con.execute("INSERT INTO order_items VALUES (?,?,?,?,?)",
                        (item_id, order_id, pid, rnd.randint(1, 3), round(price, 2)))
            item_id += 1

    con.commit()
    con.close()
    return path


if __name__ == "__main__":
    print(f"Oluşturuldu: {build()}")
