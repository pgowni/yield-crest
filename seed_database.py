from pathlib import Path
import sqlite3

if __name__ == "__main__":
    path = Path(__file__).with_name("yieldcrest_step2.sqlite")
    if path.exists():
        raise SystemExit("Database already exists.")
    with sqlite3.connect(path) as db:
        db.executescript(path.with_name("seed_history.sql").read_text())
