import sqlite3

conn = sqlite3.connect("ecocoin.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(users)")
cols = [r[1] for r in cur.fetchall()]
if "secret_pin" not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN secret_pin TEXT")
    print("✅ Added secret_pin column")

conn.commit()
conn.close()
