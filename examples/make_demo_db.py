"""Create a small, fully synthetic sales database.

Every person, email and phone number here is invented. Do not replace them
with real data; use invented records for testing (Chapter 7, canary tests).

    python examples/make_demo_db.py                 # healthy data
    python examples/make_demo_db.py --break-feed    # half the invoice lines never arrive (Chapter 21)
"""
import argparse
import os
import random
import sqlite3

FIRST = ["Ada", "Bora", "Cem", "Defne", "Elif", "Faruk", "Gul", "Hakan", "Ipek", "Jale",
         "Kerem", "Leyla", "Mert", "Nil", "Oya", "Pelin", "Rana", "Selim", "Tuna", "Umay"]
LAST = ["Testoglu", "Ornekci", "Kurgu", "Sahte", "Deneme", "Uydurma"]
CITIES = ["Istanbul", "Ankara", "Izmir", "Bursa", "Heidelberg", "Mannheim"]
SEGMENTS = ["retail", "wholesale", "online"]
PRODUCTS = [("Copper wire 2.5mm", "cable", 4.20), ("Copper wire 4mm", "cable", 6.80),
            ("Junction box", "fittings", 3.10), ("Cable tray 3m", "fittings", 18.50),
            ("Circuit breaker 16A", "protection", 9.90), ("RCD 40A", "protection", 34.00),
            ("LED panel 60x60", "lighting", 27.00), ("Floodlight 50W", "lighting", 22.50)]


def build(path, break_feed=False, seed=7):
    rnd = random.Random(seed)
    if os.path.exists(path):
        os.remove(path)
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT, phone TEXT,
                            city TEXT, segment TEXT);
    CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, unit_price REAL);
    CREATE TABLE invoices (id INTEGER PRIMARY KEY, customer_id INTEGER, invoice_date TEXT, total REAL);
    CREATE TABLE invoice_lines (id INTEGER PRIMARY KEY, invoice_id INTEGER, product_id INTEGER,
                                quantity INTEGER, unit_price REAL);
    """)
    for i in range(1, 41):
        name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        email = name.lower().replace(" ", ".") + f"{i}@example.invalid"
        phone = f"+90 555 {rnd.randint(100, 999)} {rnd.randint(1000, 9999)}"
        c.execute("INSERT INTO customers VALUES (?,?,?,?,?,?)",
                  (i, name, email, phone, rnd.choice(CITIES), rnd.choice(SEGMENTS)))
    for i, (n, cat, p) in enumerate(PRODUCTS, 1):
        c.execute("INSERT INTO products VALUES (?,?,?,?)", (i, n, cat, p))
    line_id = 0
    for inv in range(1, 601):
        y, m = rnd.choice([2025, 2026]), rnd.randint(1, 12)
        if y == 2026 and m > 9:
            m = rnd.randint(1, 9)
        date = f"{y}-{m:02d}-{rnd.randint(1, 28):02d}"
        cust = rnd.randint(1, 40)
        total = 0.0
        lines = []
        for _ in range(rnd.randint(1, 4)):
            pid = rnd.randint(1, len(PRODUCTS))
            q = rnd.randint(1, 50)
            price = PRODUCTS[pid - 1][2]
            line_id += 1
            lines.append((line_id, inv, pid, q, price))
            total += q * price
        c.execute("INSERT INTO invoices VALUES (?,?,?,?)", (inv, cust, date, round(total, 2)))
        c.executemany("INSERT INTO invoice_lines VALUES (?,?,?,?,?)", lines)
    if break_feed:
        # The delivery stopped half way: many invoices arrive without their lines.
        c.execute("DELETE FROM invoice_lines WHERE invoice_id % 2 = 0")
    c.commit()
    c.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.path.join(os.path.dirname(__file__), "demo.db"))
    ap.add_argument("--break-feed", action="store_true")
    a = ap.parse_args()
    build(a.path, a.break_feed)
    print("Created", a.path, "(broken feed)" if a.break_feed else "")
