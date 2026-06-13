"""
Unified SQLite storage for all imported databases.
"""
import sqlite3
import os
import sys

# Frozen (.exe): БД лежит рядом с .exe в папке data/
# Dev: рядом со скриптом в ../data/
if getattr(sys, 'frozen', False):
    _data_dir = os.path.join(os.path.dirname(sys.executable), 'data')
else:
    _data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

os.makedirs(_data_dir, exist_ok=True)
DB_PATH = os.path.join(_data_dir, 'cronos_mac.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT NOT NULL UNIQUE,
            type    TEXT NOT NULL,          -- 'cronos' | 'csv' | 'sql'
            path    TEXT,
            imported_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS records (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL REFERENCES sources(id),
            table_name TEXT NOT NULL,
            rec_id    INTEGER,
            data      TEXT NOT NULL         -- JSON
        );

        CREATE TABLE IF NOT EXISTS fields (
            source_id  INTEGER NOT NULL REFERENCES sources(id),
            table_name TEXT NOT NULL,
            field_name TEXT NOT NULL,
            PRIMARY KEY (source_id, table_name, field_name)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS records_fts
            USING fts5(data, content='records', content_rowid='id');

        CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
            INSERT INTO records_fts(rowid, data) VALUES (new.id, new.data);
        END;
    """)
    conn.commit()
    conn.close()
