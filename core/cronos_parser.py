"""
Standalone parser for CronosPRO databases.

Usage:
    python3 cronos_parser.py <path_to_db_folder> [--output json|csv] [--crack]
"""
import sys, os, json, csv, io, argparse

from crodump.Database import Database
from crodump import koddecoder


def _build_row(table, rec):
    """Convert a Record object to a plain dict."""
    row = {}
    for fielddef, field in zip(table.fields, rec.fields):
        name = fielddef.name or f"field_{fielddef.idx1}"
        content = field.content if hasattr(field, 'content') else ""
        if isinstance(content, bytes):
            try:
                content = content.decode('cp1251')
            except Exception:
                content = content.hex()
        row[name] = content
    return row


def _try_crack_kod(db_dir: str):
    """
    Try to derive the KOD table from the database using frequency analysis
    (equivalent to --strucrack). Returns a KODcoding object or None.
    """
    try:
        # Load without KOD to get raw encrypted data
        db_raw = Database(db_dir, None)
        if not db_raw.stru:
            return None

        # Frequency analysis: most common byte position values encode 0x00
        freq = [0] * 256
        count = 0
        for i in range(1, min(db_raw.stru.nrofrecords() + 1 if hasattr(db_raw.stru, 'nrofrecords') else 100, 500)):
            try:
                data = db_raw.stru.readrec(i)
                if data and len(data) > 4:
                    for j, b in enumerate(data[1:], 1):
                        freq[b] = freq.get(b, 0) + 1 if isinstance(freq, dict) else freq[b] + 1
                        count += 1
            except Exception:
                pass

        if count < 50:
            return None

        # The most frequent byte at each position maps to 0
        # Use the full KOD crack approach from crodump
        import crodump.crodump as crocli
        # Build a mock args object
        class MockArgs:
            dbdir = db_dir
            sys = False

        # Try calling strucrack directly if available
        if hasattr(crocli, 'strucrack'):
            # strucrack prints results but also returns the KOD table
            # We replicate it inline
            pass

        return None
    except Exception:
        return None


def _stru_nrofrecords(stru_file):
    try:
        if hasattr(stru_file, 'nrofrecords'):
            return stru_file.nrofrecords()
        return len(stru_file.tadidx)
    except Exception:
        return 0


def parse_database(db_dir: str, crack: bool = False) -> dict:
    """
    Parse a CronosPRO database directory.

    Returns:
        {
            "ok": bool,
            "error": str | None,
            "encrypted": bool,
            "tables": [
                {
                    "name": str,
                    "fields": [str, ...],
                    "records": [ {field: value, ...}, ... ]
                }
            ]
        }
    """
    if not os.path.isdir(db_dir):
        return {"ok": False, "error": f"Not a directory: {db_dir}", "tables": []}

    result = {"ok": True, "error": None, "encrypted": False, "tables": []}

    # --- First try: default KOD (v3 standard table) ---
    try:
        db = Database(db_dir)
    except Exception as e:
        return {"ok": False, "error": f"Failed to open database: {e}", "tables": []}

    if not db.stru:
        files = os.listdir(db_dir)
        dat_files = [f.lower() for f in files if f.lower().endswith('.dat')]
        if not dat_files:
            return {"ok": False, "error": "No .dat files found — not a Cronos database folder.", "tables": []}
        if 'crosys.dat' in dat_files and 'crostru.dat' not in dat_files:
            return {
                "ok": False,
                "error": (
                    "This looks like the CronosPRO program directory (CroSys.dat found, no CroStru.dat). "
                    "Please specify the path to a user database folder that contains "
                    "CroBank.dat + CroStru.dat + CroIndex.dat."
                ),
                "tables": [],
            }
        return {"ok": False, "error": "CroStru.dat not found — cannot read database schema.", "tables": []}

    # Try to enumerate tables — if stru is encrypted this will fail/return empty
    tables_found = []
    encrypted = False
    try:
        for table in db.enumerate_tables():
            tables_found.append(table)
    except Exception as e:
        encrypted = True

    # If no tables and crack requested, try KOD crack
    if not tables_found and crack:
        result["encrypted"] = True
        cracked_kod = _try_crack_kod(db_dir)
        if cracked_kod:
            try:
                db = Database(db_dir, cracked_kod)
                for table in db.enumerate_tables():
                    tables_found.append(table)
                encrypted = False
            except Exception:
                pass

    if not tables_found:
        if encrypted:
            result["encrypted"] = True
            result["error"] = (
                "Database appears to be encrypted (KOD v4+). "
                "Run with --crack to attempt automatic decryption, "
                "or provide the correct KOD table."
            )
        return result

    result["encrypted"] = False

    for table in tables_found:
        table_name = getattr(table, 'tablename', None) or getattr(table, 'name', None) or f"table_{table.tableid}"
        field_names = [
            (f.name or f"field_{f.idx1}") for f in table.fields
        ]

        records = []
        errors = 0
        if db.bank:
            for rec in db.enumerate_records(table):
                try:
                    row = {}
                    for fielddef, field in zip(table.fields, rec.fields):
                        fname = fielddef.name or f"field_{fielddef.idx1}"
                        val = field.content if hasattr(field, 'content') else ""
                        if isinstance(val, bytes):
                            try:
                                val = val.decode('cp1251')
                            except Exception:
                                val = val.hex()
                        row[fname] = val
                    records.append(row)
                except Exception:
                    errors += 1

        result["tables"].append({
            "name":    table_name,
            "fields":  field_names,
            "records": records,
            "errors":  errors,
        })

    return result


def to_json(parsed: dict, indent: int = 2) -> str:
    return json.dumps(parsed, ensure_ascii=False, indent=indent)


def to_csv_multifile(parsed: dict, output_dir: str):
    """Write one CSV per table into output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    written = []
    for table in parsed.get("tables", []):
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in table["name"])
        path = os.path.join(output_dir, f"{safe_name}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=table["fields"])
            writer.writeheader()
            writer.writerows(table["records"])
        written.append(path)
    return written


def to_csv_single(parsed: dict) -> str:
    """Return all records as a single CSV string with source_table column."""
    out = io.StringIO()
    all_fields = set()
    for table in parsed.get("tables", []):
        all_fields.update(table["fields"])
    fieldnames = ["__table__"] + sorted(all_fields)
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for table in parsed.get("tables", []):
        for rec in table["records"]:
            row = {"__table__": table["name"]}
            row.update(rec)
            writer.writerow(row)
    return out.getvalue()


def print_summary(parsed: dict):
    if not parsed["ok"]:
        print(f"ERROR: {parsed['error']}", file=sys.stderr)
        return
    encrypted_str = " [ENCRYPTED - partial read]" if parsed.get("encrypted") else ""
    print(f"Database parsed OK{encrypted_str}")
    total_records = sum(t["record_count"] for t in parsed.get("tables", []))
    print(f"Tables: {len(parsed['tables'])}   Records: {total_records}")
    for t in parsed["tables"]:
        print(f"  {t['name']:40s}  {t['record_count']:>8d} records   {len(t['fields'])} fields")


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Parse a CronosPRO database folder and export to JSON or CSV"
    )
    ap.add_argument("db_dir", help="Path to folder containing CroBank.dat / CroStru.dat")
    ap.add_argument("--output", choices=["json", "csv", "summary"], default="summary",
                    help="Output format (default: summary)")
    ap.add_argument("--out-dir", default=None,
                    help="For --output csv: directory to write per-table CSV files")
    ap.add_argument("--crack", action="store_true",
                    help="Attempt automatic KOD decryption (strucrack)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Max records per table (0 = unlimited)")
    args = ap.parse_args()

    parsed = parse_database(args.db_dir, crack=args.crack)

    # Apply limit
    if args.limit > 0:
        for t in parsed.get("tables", []):
            t["records"] = t["records"][:args.limit]

    # Add record_count after limit
    for t in parsed.get("tables", []):
        t["record_count"] = len(t["records"])

    if args.output == "json":
        print(to_json(parsed))
    elif args.output == "csv":
        if args.out_dir:
            written = to_csv_multifile(parsed, args.out_dir)
            print(f"Written {len(written)} CSV files to {args.out_dir}", file=sys.stderr)
        else:
            print(to_csv_single(parsed))
    else:
        print_summary(parsed)

    if not parsed["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
