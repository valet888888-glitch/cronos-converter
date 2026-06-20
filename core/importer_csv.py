"""
Import CSV / SQL / TXT files into unified DB.
"""
import csv, json, os, io, re, sys
import chardet
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2_147_483_647)
from .db import get_conn


def detect_encoding(path: str) -> str:
    with open(path, 'rb') as f:
        raw = f.read(65536)
    result = chardet.detect(raw)
    enc = result.get('encoding') or 'utf-8'
    # normalise common Russian encodings
    enc = enc.lower().replace('-', '')
    if enc in ('cp1251', 'windows1251'):
        return 'cp1251'
    if enc in ('koi8r',):
        return 'koi8-r'
    return result.get('encoding') or 'utf-8'


def _looks_like_sql(path: str) -> bool:
    """Return True if the file content looks like a SQL dump (not a CSV/TXT)."""
    try:
        with open(path, 'rb') as f:
            head = f.read(4096).decode('utf-8', errors='replace').lstrip()
        upper = head.upper()
        return any(kw in upper for kw in ('INSERT INTO', 'CREATE TABLE', 'DROP TABLE', '-- MYSQL'))
    except Exception:
        return False


def import_csv(path: str, source_name: str = None, table_name: str = None) -> dict:
    source_name = source_name or os.path.basename(path)
    # Derive table name from source_name (original filename), not path (may be a temp file)
    table_name  = table_name  or os.path.splitext(os.path.basename(source_name))[0]
    encoding    = detect_encoding(path)

    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO sources(name, type, path) VALUES (?,?,?)",
        (source_name, 'csv', path)
    )
    conn.execute(
        "UPDATE sources SET path=?, imported_at=datetime('now') WHERE name=?",
        (path, source_name)
    )
    source_id = conn.execute(
        "SELECT id FROM sources WHERE name=?", (source_name,)
    ).fetchone()["id"]
    # Remove old records for re-import
    conn.execute("DELETE FROM records WHERE source_id=?", (source_id,))
    conn.commit()

    stats = {"records": 0, "errors": 0}

    with open(path, encoding=encoding, errors='replace', newline='') as f:
        # sniff delimiter — fall back to header-line count if sniffer fails
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        except Exception:
            # Count delimiters in the header line only
            header_line = sample.split('\n')[0].lstrip('(')
            counts = {d: header_line.count(d) for d in (',', ';', '\t', '|')}
            best_delim = max(counts, key=counts.get) if max(counts.values()) > 0 else ','
            dialect = csv.excel
            dialect = type('D', (), {'delimiter': best_delim, 'quotechar': '"',
                                     'doublequote': True, 'skipinitialspace': False,
                                     'lineterminator': '\n', 'quoting': csv.QUOTE_MINIMAL})()

        # Strip leading '(' from rows if present (Bitrix/Cronos export format)
        first_data = sample.split('\n')[1] if '\n' in sample else ''
        strip_parens = first_data.lstrip().startswith('(')

        def _clean_lines(fh):
            for ln in fh:
                ln = ln.replace('\x00', '')
                s = ln.lstrip()
                if strip_parens and s.startswith('('):
                    ln = s[1:]
                yield ln

        src = _clean_lines(f)
        reader = csv.DictReader(src, dialect=dialect)
        field_names = reader.fieldnames or []

        conn.executemany(
            "INSERT OR IGNORE INTO fields(source_id, table_name, field_name) VALUES (?,?,?)",
            [(source_id, table_name, fn) for fn in field_names]
        )

        batch = []
        for i, row in enumerate(reader):
            batch.append((source_id, table_name, i + 1,
                          json.dumps(dict(row), ensure_ascii=False)))
            stats["records"] += 1
            if len(batch) >= 1000:
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


def import_txt(path: str, source_name: str = None, table_name: str = None) -> dict:
    """Import a TXT file as delimited data (same pipeline as CSV with auto-detect)."""
    return import_csv(path, source_name=source_name, table_name=table_name)


def import_sql(path: str, source_name: str = None) -> dict:
    """
    Parse a MySQL/PostgreSQL dump and import INSERT rows.
    """
    source_name = source_name or os.path.basename(path)
    encoding    = detect_encoding(path)

    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO sources(name, type, path) VALUES (?,?,?)",
        (source_name, 'sql', path)
    )
    conn.execute(
        "UPDATE sources SET path=?, imported_at=datetime('now') WHERE name=?",
        (path, source_name)
    )
    source_id = conn.execute(
        "SELECT id FROM sources WHERE name=?", (source_name,)
    ).fetchone()["id"]
    conn.execute("DELETE FROM records WHERE source_id=?", (source_id,))
    conn.commit()

    stats = {"tables": 0, "records": 0, "errors": 0}
    current_table = None
    current_cols  = []

    # Patterns for CREATE TABLE and INSERT INTO
    re_create  = re.compile(r'CREATE TABLE[^`]*`?(\w+)`?', re.I)
    re_cols    = re.compile(r'`(\w+)`\s+\w', re.I)
    re_insert  = re.compile(r'INSERT\s+INTO\s+`?(\w+)`?\s*(?:\(([^)]+)\))?\s*VALUES\s*', re.I)

    def _parse_values_row(s):
        """Parse one SQL values tuple like ('a','b\\'c',NULL,1) into a list of strings."""
        vals = []
        i = 0
        n = len(s)
        cur = []
        while i < n:
            c = s[i]
            if c in ("'", '"'):
                q = c
                i += 1
                while i < n:
                    c2 = s[i]
                    if c2 == '\\':
                        cur.append(s[i+1] if i+1 < n else '')
                        i += 2
                        continue
                    if c2 == q:
                        i += 1
                        break
                    cur.append(c2)
                    i += 1
            elif c == ',':
                vals.append(''.join(cur))
                cur = []
                i += 1
            elif c == ')':
                break
            else:
                cur.append(c)
                i += 1
        vals.append(''.join(cur))
        return vals

    def _flush_batch(batch):
        if batch:
            conn.executemany(
                "INSERT INTO records(source_id,table_name,rec_id,data) VALUES (?,?,?,?)",
                batch
            )
            conn.commit()
            batch.clear()

    batch = []
    # State machine for multi-line INSERT statements
    in_insert = False
    insert_tbl = None
    insert_cols = []
    buf_lines = []

    with open(path, encoding=encoding, errors='replace') as f:
        for raw_line in f:
            line = raw_line.rstrip('\n').rstrip('\r')

            # Detect CREATE TABLE
            mc = re_create.search(line)
            if mc and not in_insert:
                current_table = mc.group(1)
                current_cols  = []
                stats["tables"] += 1
                continue

            if not in_insert:
                # Extract column names from CREATE TABLE body
                if current_table and re_cols.search(line):
                    current_cols += re_cols.findall(line)

                mi = re_insert.search(line)
                if mi:
                    insert_tbl  = mi.group(1)
                    insert_cols = [c.strip().strip('`') for c in mi.group(2).split(',')] \
                                  if mi.group(2) else list(current_cols)
                    if insert_cols:
                        conn.executemany(
                            "INSERT OR IGNORE INTO fields(source_id,table_name,field_name) "
                            "VALUES (?,?,?)",
                            [(source_id, insert_tbl, c) for c in insert_cols]
                        )
                    # Values start after VALUES keyword on the same line
                    rest = line[mi.end():]
                    buf_lines = [rest]
                    in_insert = True
                continue

            # Accumulate multi-line INSERT
            buf_lines.append(line)

            # Check if statement is complete
            combined = ' '.join(buf_lines)
            # Find all complete row tuples in the accumulated buffer
            depth = 0
            row_start = -1
            i = 0
            consumed_to = 0
            while i < len(combined):
                ch = combined[i]
                if ch == '(' and depth == 0:
                    depth = 1
                    row_start = i + 1
                elif ch == '(' and depth > 0:
                    depth += 1
                elif ch == ')' and depth > 1:
                    depth -= 1
                elif ch == ')' and depth == 1:
                    depth = 0
                    row_str = combined[row_start:i]
                    vals = _parse_values_row(row_str)
                    vals = [v.strip() if v.strip().upper() != 'NULL' else '' for v in vals]
                    cols = insert_cols or current_cols
                    row = dict(zip(cols, vals)) if cols else {"raw": row_str[:200]}
                    batch.append((source_id, insert_tbl, stats["records"] + 1,
                                  json.dumps(row, ensure_ascii=False)))
                    stats["records"] += 1
                    consumed_to = i + 1
                    if len(batch) >= 500:
                        _flush_batch(batch)
                elif ch in ("'", '"'):
                    q = ch
                    i += 1
                    while i < len(combined):
                        if combined[i] == '\\':
                            i += 2
                            continue
                        if combined[i] == q:
                            break
                        i += 1
                i += 1

            # Statement ends with ';'
            if combined.rstrip().endswith(';'):
                in_insert = False
                buf_lines = []
                consumed_to = len(combined)
            elif consumed_to > 0:
                # Keep only unprocessed tail
                buf_lines = [combined[consumed_to:].lstrip(', \t')]

    _flush_batch(batch)
    conn.close()
    return stats
