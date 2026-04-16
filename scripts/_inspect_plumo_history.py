#!/usr/bin/env python3
import psycopg2

DBS = [
    ("PROD", 5432, "plumo",     "plumo", "plumo"),
    ("DEV",  5433, "plumo_dev", "plumo", "plumo"),
]

for label, port, db, user, pwd in DBS:
    try:
        conn = psycopg2.connect(host="localhost", port=port, database=db, user=user, password=pwd)
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'migration_history' ORDER BY ordinal_position"
        )
        cols = cur.fetchall()
        print(f"\n{label}: columns = {[c[0] for c in cols]}")
        cur.execute("SELECT * FROM migration_history ORDER BY 1")
        for r in cur.fetchall():
            print(f"  {r}")
        conn.close()
    except Exception as e:
        print(f"\n{label}: erro - {e}")
