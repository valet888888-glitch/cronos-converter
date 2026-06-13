"""
Import CronosPRO databases (CroBank/CroStru/CroIndex) via cronodump.
"""
import sys, os, json
sys.path.insert(0, '/Users/greguar_x/Library/Python/3.9/lib/python/site-packages')

from .cronos_parser import parse_database
from .db import get_conn


def import_cronos(db_dir: str, source_name: str, crack: bool = False) -> dict:
    conn = get_conn()

    conn.execute(
        "INSERT OR IGNORE INTO sources(name, type, path) VALUES (?,?,?)",
        (source_name, 'cronos', db_dir)
    )
    conn.execute(
        "UPDATE sources SET path=?, imported_at=datetime('now') WHERE name=?",
        (db_dir, source_name)
    )
    source_id = conn.execute(
        "SELECT id FROM sources WHERE name=?", (source_name,)
    ).fetchone()["id"]
    conn.execute("DELETE FROM records WHERE source_id=?", (source_id,))
    conn.commit()

    parsed = parse_database(db_dir, crack=crack)

    if not parsed["ok"]:
        conn.close()
        return {"error": parsed["error"], "encrypted": parsed.get("encrypted", False)}

    stats = {"tables": 0, "records": 0, "errors": 0,
             "encrypted": parsed.get("encrypted", False)}

    for table in parsed["tables"]:
        table_name = table["name"]
        field_names = table["fields"]
        stats["tables"] += 1
        stats["errors"] += table.get("errors", 0)

        conn.executemany(
            "INSERT OR IGNORE INTO fields(source_id, table_name, field_name) VALUES (?,?,?)",
            [(source_id, table_name, fn) for fn in field_names]
        )

        batch = []
        for i, row in enumerate(table["records"]):
            batch.append((
                source_id, table_name, i + 1,
                json.dumps(row, ensure_ascii=False)
            ))
            stats["records"] += 1
            if len(batch) >= 500:
                conn.executemany(
                    "INSERT INTO records(source_id,table_name,rec_id,data) VALUES (?,?,?,?)",
                    batch
                )
                conn.commit()
                batch = []

        if batch:
            conn.executemany(
                "INSERT INTO records(source_id,table_name,rec_id,data) VALUES (?,?,?,?)",
                batch
            )
            conn.commit()

    conn.close()
    return stats
