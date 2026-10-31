from pathlib import Path
import random
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/runtime/retail.db"
random.seed(53)
products = [("Trail Mug", "outdoors"), ("Desk Lamp", "home"), ("Notebook Set", "office"), ("Rain Shell", "outdoors"), ("Cable Kit", "electronics"), ("Storage Box", "home")]
DB.parent.mkdir(parents=True, exist_ok=True)
if DB.exists():
    DB.unlink()
with sqlite3.connect(DB) as con:
    con.execute("CREATE TABLE orders(order_id TEXT, order_date TEXT, product TEXT, category TEXT, quantity INTEGER, gross REAL, refund REAL)")
    rows = []
    for month in range(1, 13):
        for order in range(85):
            product, category = random.choice(products)
            qty = random.randint(1, 5)
            unit = round(random.uniform(8, 120), 2)
            gross = round(unit * qty, 2)
            refund = round(gross * random.choice([0, 0, 0, 0.1, 0.25]), 2)
            rows.append((f"SYN-{month:02}-{order:03}", f"2025-{month:02}-15", product, category, qty, gross, refund))
    con.executemany("INSERT INTO orders VALUES(?,?,?,?,?,?,?)", rows)
print(f"Created {len(rows)} synthetic order lines at {DB}")
