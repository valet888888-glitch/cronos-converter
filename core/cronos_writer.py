"""
CronosPRO database writer.
Converts table data (list of dicts) into CroBank.dat/tad + CroStru.dat/tad files.

Format: v3 (01.02), 32-bit offsets, no KOD encryption, no compression.
"""
import sys, os, struct, json, re, sqlite3, itertools, hashlib, time

from crodump import koddecoder


# ── Low-level binary helpers ───────────────────────────────────────────────

def _name(s: str) -> bytes:
    """Encode a cp1251 string with 1-byte length prefix."""
    b = s.encode('cp1251', errors='replace')
    return bytes([len(b)]) + b


def _inline(data: bytes) -> bytes:
    """Inline value in DB-definition: high bit set + length + data."""
    return struct.pack("<L", 0x80000000 | len(data)) + data


def _ref(recno: int) -> bytes:
    """Reference to another CroStru record (recno as dword)."""
    return struct.pack("<L", recno)


# ── Field type inference ────────────────────────────────────────────────────

def _infer_type(values: list) -> tuple:
    """
    Guess Cronos field type from sample values.
    Returns (type_id, maxval).
    """
    non_empty = [v for v in values if v and str(v).strip()]
    if not non_empty:
        return 2, 256  # VARCHAR default

    # INTEGER heuristic
    int_count = sum(1 for v in non_empty if re.fullmatch(r'-?\d+', str(v).strip()))
    if int_count == len(non_empty):
        return 1, 20

    # DATE heuristic
    date_count = sum(1 for v in non_empty
                     if re.fullmatch(r'\d{2,4}[-./]\d{1,2}[-./]\d{1,4}', str(v).strip()))
    if date_count / max(len(non_empty), 1) > 0.8:
        return 4, 10

    max_len = max(len(str(v)) for v in non_empty)
    # Use type 2 (VARCHAR) for all text — type 3 (Dictionary) requires Voc folder
    return 2, min(max(max_len + 50, 64), 65535)


# ── FieldDefinition encoder ─────────────────────────────────────────────────

def _encode_field(idx: int, name: str, typ: int, maxval: int = 256) -> bytes:
    """Build raw bytes for a single FieldDefinition."""
    d = bytearray()
    d += struct.pack("<H", typ)
    d += struct.pack("<L", idx)
    d += _name(name)
    d += struct.pack("<L", 0)              # flags
    d += bytes([1 if typ else 0])          # minval: 0 for sysnum, 1 for others
    if typ:
        d += struct.pack("<L", idx)        # idx2
        d += struct.pack("<L", maxval)     # maxval
        d += struct.pack("<L", 0x10019)    # unk4 — confirmed value from real Cronos 5 files
        d += b"\x00" * 13                 # trailing zeros — present in all real Cronos 5 files
    return bytes(d)


# ── TableDefinition encoder ─────────────────────────────────────────────────

def _encode_table(tableid: int, name: str, field_defs: list, record_count: int = 0) -> bytes:
    """Build raw bytes for a TableDefinition (stored as CroStru record)."""
    d = bytearray()
    d += struct.pack("<H", 0)              # unk1
    d += bytes([3])                        # version = 3
    d += bytes([0])                        # padding (version > 1)
    d += bytes([9])                        # unk2 = 9
    d += bytes([1])                        # unk3 = 1
    d += struct.pack("<L", 2)              # extra dword (unk2 > 5)
    d += struct.pack("<L", record_count)   # record count (unk4)
    d += struct.pack("<L", tableid)        # tableid
    abbrev = name[:2]
    d += _name(name)
    d += _name(abbrev)
    d += struct.pack("<L", 1)              # unk7
    d += struct.pack("<L", len(field_defs))  # nrfields

    for fdef in field_defs:
        d += struct.pack("<H", len(fdef))
        d += fdef

    # Section 2 (minimal — reader handles missing gracefully)
    d += struct.pack("<L", 0)              # extraunkdatastrings = 0
    d += struct.pack("<L", 0)             # unk8
    d += bytes([2])                        # section marker 0x02
    d += struct.pack("<L", 0)             # unk9
    d += struct.pack("<L", 0)             # nrextrafields = 0
    d += struct.pack("<L", 0)             # terminator (expected by reader)

    return bytes(d)


# ── DB-definition record (CroStru record #1) ────────────────────────────────

def _encode_dbdef(db_name: str, table_recnos: list) -> bytes:
    """Build CroStru record #1 — the top-level database definition."""
    d = bytearray()
    d += bytes([0x03])                     # record type marker

    # Bank metadata — byte 1 is the format-version indicator (5 = Cronos 5)
    d += _name("Bank")
    d += _inline(b"\x00\x05" + b"\x00" * 9)

    # Unique 8-digit decimal ID — avoids conflict when multiple banks share the same
    # Cronos registry (CroSys.dat). Hardcoded "00000001" conflicts with existing banks.
    h = int(hashlib.md5(db_name.encode('utf-8', errors='replace')).hexdigest(), 16)
    bank_id_str = str((h % 89999998) + 10000001)  # range [10000001, 99999999]
    d += _name("BankId")
    d += _inline(bank_id_str.encode('ascii'))

    name_b = db_name.encode('cp1251', errors='replace')
    d += _name("BankName")
    d += _inline(name_b)

    # Base000 — Files table (always present, inline)
    sysnum_fdef = _encode_field(0, "Системный номер", 0)
    name_fdef   = _encode_field(1, "Name", 2, 256)
    files_def   = _encode_table(0, "Files", [sysnum_fdef, name_fdef])
    d += _name("Base000")
    d += _inline(files_def)

    # Formuls entries
    d += _name("Formuls000")
    d += _inline(b"\x00" * 8)
    d += _name("Formuls001")
    d += _inline(b"\x00" * 8)

    # BaseNNN for each user table (reference to CroStru records)
    for i, recno in enumerate(table_recnos, 1):
        d += _name(f"Base{i:03d}")
        d += _ref(recno)

    # NS2 — 0 means no password / open bank (NS1 omitted to avoid serial check)
    d += _name("NS2")
    d += _inline(struct.pack("<L", 0x00))

    # Version — b"\x2d\x35" = ASCII "-5" (Cronos 5 marker; "-6" caused rejection in Cronos 5)
    d += _name("Version")
    d += _inline(b"\x2d\x35")

    return bytes(d)


# ── CroFile .dat / .tad writer (v4, 01.11, 64-bit) ───────────────────────────

# Cronos 5 uses format "01.11" (v4).  All .dat files start with a fixed
# 0x300-byte header area; record offsets in the TAD are relative to file start.
_DAT_HEADER_AREA = 0x300   # 19 bytes header + 0xE9 random pad + 0x204 zero pad

def _write_dat_header(f, encoding: int, blocksize: int):
    """Write the 0x300-byte header area of a v4 CroFile .dat file."""
    f.write(b"CroFile\x00")
    f.write(struct.pack("<H", 0x0206))     # hdrunk — matches CronosPRO v4 format
    f.write(b"01.11")                      # version — v4, 64-bit
    f.write(struct.pack("<H", encoding))   # encoding: 0=plain, 1=KOD
    f.write(struct.pack("<H", blocksize))
    f.write(b"\x00" * 0xE9)               # traditional random-padding area
    # Pad to _DAT_HEADER_AREA total
    written = 19 + 0xE9
    f.write(b"\x00" * (_DAT_HEADER_AREA - written))


def _write_tad_header(f):
    """Write the 16-byte v4 TAD file header."""
    f.write(struct.pack("<LLLL", 0xFFFFFFFE, 0, 0, 0))


def _write_tad_entry(f, offset: int, ln: int, chk: int = 0, flags: int = 0x04):
    """
    Write one 16-byte v4 TAD entry.
    flags=0x04 → inline data (no ext-rec prefix), same as v3 0x80.
    flags=0x00 → ext-rec (data prefixed with extofs+extlen).
    """
    Q = (flags << 56) | offset
    f.write(struct.pack("<QLL", Q, ln, chk))


class _CroFileWriter:
    """Build a pair of .dat + .tad CronosPRO files (v4, 01.11, 64-bit)."""

    def __init__(self, blocksize: int = 0x40, encoding: int = 0):
        self.blocksize = blocksize
        self.encoding = encoding
        self._records: list[bytes] = []

    def add_record(self, data: bytes):
        self._records.append(data)

    def build(self) -> tuple[bytes, bytes]:
        dat = bytearray(b"\x00" * _DAT_HEADER_AREA)
        # Write proper header into the first 19+0xE9 bytes
        struct.pack_into("<8sH5sHH", dat, 0,
                         b"CroFile\x00", 0x0206, b"01.11",
                         self.encoding, self.blocksize)

        tad = bytearray()
        _write_tad_header_bytes(tad)

        kod = koddecoder.new()
        for i, rec in enumerate(self._records):
            recno = i + 1
            if self.encoding & 1:
                # v4 format: [8 zero bytes][4-byte LE content_len][KOD-encoded content][zero padding]
                # Only the content portion is KOD-encoded; the 12-byte header is stored plain.
                encdata = kod.encode(recno, rec)
                raw_block = b"\x00" * 8 + struct.pack("<L", len(rec)) + encdata
            else:
                raw_block = rec
            padded_len = ((len(raw_block) + self.blocksize - 1) // self.blocksize) * self.blocksize
            padded = raw_block + b"\x00" * (padded_len - len(raw_block))
            offset = len(dat)
            _write_tad_entry_bytes(tad, offset, padded_len, flags=0x08)
            dat += padded

        return bytes(dat), bytes(tad)


def _write_tad_header_bytes(buf: bytearray):
    buf += struct.pack("<LLLL", 0xFFFFFFFE, 0, 0, 0)


def _write_tad_entry_bytes(buf: bytearray, offset: int, ln: int,
                           chk: int = 0, flags: int = 0x04):
    Q = (flags << 56) | offset
    buf += struct.pack("<QLL", Q, ln, chk)


# ── CroBank record encoder ────────────────────────────────────────────────────

_SAFE_CTRL = frozenset([0x09, 0x0a, 0x0d])  # TAB, LF, CR are OK in values

def _encode_bank_record(tableid: int, fields: list, row: dict) -> bytes:
    """
    Build a CroBank v4 record.
    v4 format: [8 zero bytes] + [4-byte LE content_len] + [tableid byte] + [fields sep by 0x1E]
    TAD flags must be 0x08 (inline v4 record).
    """
    parts = []
    for fname in fields[1:]:
        val = str(row.get(fname, "") or "")
        enc = val.encode('cp1251', errors='replace')
        enc = bytes(b for b in enc if b >= 0x20 or b in _SAFE_CTRL)
        parts.append(enc)
    content = bytes([tableid]) + b"\x1e".join(parts)
    return b"\x00" * 8 + struct.pack("<L", len(content)) + content


# ── Streaming CroBank writer ──────────────────────────────────────────────────

def _write_bank_streaming(records_iter, dat_path, tad_path, blocksize=0x0040):
    """Write CroBank .dat/.tad directly from a record iterator — v4 (01.11, 64-bit)."""
    with open(dat_path, 'wb') as df, open(tad_path, 'wb') as tf:
        _write_dat_header(df, encoding=0, blocksize=blocksize)
        _write_tad_header(tf)
        for rec in records_iter:
            offset = df.tell()
            # Pad record to multiple of blocksize — CronosPRO requires aligned record sizes
            padded_len = ((len(rec) + blocksize - 1) // blocksize) * blocksize
            _write_tad_entry(tf, offset, padded_len, flags=0x08)
            df.write(rec)
            if padded_len > len(rec):
                df.write(b'\x00' * (padded_len - len(rec)))
        df.flush()
        os.fsync(df.fileno())
        tf.flush()
        os.fsync(tf.fileno())


# ── Public API ────────────────────────────────────────────────────────────────

def write_cronos(tables: list, output_dir: str, db_name: str = "export") -> dict:
    """
    Write a CronosPRO database to output_dir.

    tables: list of dicts:
        {
            "name": str,
            "fields": [str, ...],    # field names (no sysnum needed)
            "records": [{field: val, ...}, ...]
        }

    Returns stats dict.
    """
    os.makedirs(output_dir, exist_ok=True)
    stats = {"tables": 0, "records": 0}

    stru  = _CroFileWriter(blocksize=0x0400, encoding=1)  # KOD-encrypted, matches reference
    index = _CroFileWriter(blocksize=0x0400)

    table_recnos  = []
    table_entries = []  # (tableid, all_fields, records_iterable)

    for t_idx, table in enumerate(tables):
        tableid = t_idx + 1
        tname   = table["name"]
        fnames  = table.get("fields", [])
        records = table.get("records", [])

        user_fields = [f for f in fnames if f not in ("Системный номер", "__recno__")]
        all_fields  = ["Системный номер"] + user_fields

        # Support both list and generator: peek first 100 for type inference
        if isinstance(records, (list, tuple)):
            sample       = records[:100]
            records_iter = iter(records)
            record_count = len(records)
        else:
            it           = iter(records)
            sample       = list(itertools.islice(it, 100))
            records_iter = itertools.chain(sample, it)
            record_count = 0  # unknown for generators

        field_defs = [_encode_field(0, "Системный номер", 0)]
        for i, fname in enumerate(user_fields, 1):
            samples = [r.get(fname, "") for r in sample]
            typ, maxval = _infer_type(samples)
            field_defs.append(_encode_field(i, fname, typ, maxval))

        tdef_bytes = _encode_table(tableid, tname, field_defs, record_count=record_count)
        stru_recno = len(stru._records) + 1
        stru.add_record(b"\x04" + tdef_bytes)
        table_recnos.append(stru_recno)
        table_entries.append((tableid, all_fields, records_iter))
        stats["tables"] += 1

    adjusted_recnos = [i + 2 for i in range(len(tables))]
    dbdef_bytes = _encode_dbdef(db_name, adjusted_recnos)
    stru._records.insert(0, dbdef_bytes)

    # Write CroStru and CroIndex (small, in memory)
    stru_dat, stru_tad   = stru.build()
    index_dat, index_tad = index.build()
    for fname, data in [
        ("CroStru.dat", stru_dat), ("CroStru.tad", stru_tad),
        ("CroIndex.dat", index_dat), ("CroIndex.tad", index_tad),
    ]:
        with open(os.path.join(output_dir, fname), "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

    # Stream CroBank directly to disk — no full in-memory copy
    def _bank_gen():
        for tableid, all_fields, rec_iter in table_entries:
            for row in rec_iter:
                stats["records"] += 1
                yield _encode_bank_record(tableid, all_fields, row)

    _write_bank_streaming(
        _bank_gen(),
        os.path.join(output_dir, "CroBank.dat"),
        os.path.join(output_dir, "CroBank.tad"),
        blocksize=0x0040,
    )

    stats["output_dir"] = output_dir
    stats["files"] = ["CroStru.dat", "CroStru.tad", "CroBank.dat",
                      "CroBank.tad", "CroIndex.dat", "CroIndex.tad"]
    return stats


def sql_to_cronos(db_conn, output_dir: str, db_name: str = "export",
                  table_names: list = None, limit: int = 0) -> dict:
    """
    Export from a SQLite connection (our internal DB) to Cronos format.
    If table_names is None, exports all tables from a single source.
    """
    db_conn.row_factory = sqlite3.Row
    cursor = db_conn.cursor()

    tables = []
    if table_names is None:
        rows = cursor.execute(
            "SELECT DISTINCT table_name FROM records LIMIT 50"
        ).fetchall()
        table_names = [r["table_name"] for r in rows]

    for tname in table_names:
        q = "SELECT data FROM records WHERE table_name=?"
        if limit > 0:
            q += f" LIMIT {limit}"
        recs = cursor.execute(q, (tname,)).fetchall()

        records = []
        fields_set = []
        for rec in recs:
            row = json.loads(rec["data"])
            records.append(row)
            for k in row:
                if k not in fields_set:
                    fields_set.append(k)

        tables.append({"name": tname, "fields": fields_set, "records": records})

    return write_cronos(tables, output_dir, db_name=db_name)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    from .db import get_conn

    ap = argparse.ArgumentParser(
        description="Convert internal DB source to CronosPRO format"
    )
    ap.add_argument("source_name", help="Source name as imported (from list_sources)")
    ap.add_argument("output_dir", help="Directory to write Cronos .dat/.tad files")
    ap.add_argument("--limit", type=int, default=0,
                    help="Max records per table (0 = all)")
    args = ap.parse_args()

    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM sources WHERE name=?", (args.source_name,)
    ).fetchone()
    if not row:
        print(f"Source '{args.source_name}' not found")
        conn.close()
        return 1

    source_id = row["id"]
    table_rows = conn.execute(
        "SELECT DISTINCT table_name FROM records WHERE source_id=?", (source_id,)
    ).fetchall()
    table_names = [r["table_name"] for r in table_rows]

    tables = []
    for tname in table_names:
        q = "SELECT data FROM records WHERE source_id=? AND table_name=?"
        params = [source_id, tname]
        if args.limit > 0:
            q += " LIMIT ?"
            params.append(args.limit)
        recs = conn.execute(q, params).fetchall()

        records = []
        fields_set = []
        for rec in recs:
            row = json.loads(rec["data"])
            records.append(row)
            for k in row:
                if k not in fields_set:
                    fields_set.append(k)

        tables.append({"name": tname, "fields": fields_set, "records": records})

    stats = write_cronos(tables, args.output_dir, db_name=args.source_name)
    conn.close()

    print(f"Written {stats['tables']} tables, {stats['records']} records → {args.output_dir}")
    for f in stats["files"]:
        path = os.path.join(args.output_dir, f)
        print(f"  {f}  ({os.path.getsize(path):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
