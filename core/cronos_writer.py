"""
CronosPRO database writer.
Converts table data (list of dicts) into CroBank.dat/tad + CroStru.dat/tad files.

Format: v3 (01.02), 32-bit offsets, no KOD encryption, no compression.
"""
import sys, os, struct, json, re, sqlite3

sys.path.insert(0, '/Users/greguar_x/Library/Python/3.9/lib/python/site-packages')
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
    if max_len > 500:
        return 3, 65535  # TEXT
    return 2, max(max_len + 50, 64)  # VARCHAR


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

def _encode_table(tableid: int, name: str, field_defs: list) -> bytes:
    """Build raw bytes for a TableDefinition (stored as CroStru record)."""
    d = bytearray()
    d += struct.pack("<H", 0)              # unk1
    d += bytes([3])                        # version = 3
    d += bytes([0])                        # padding (version > 1)
    d += bytes([9])                        # unk2 = 9
    d += bytes([1])                        # unk3 = 1
    d += struct.pack("<L", 2)              # extra dword (unk2 > 5)
    d += struct.pack("<L", 0)              # unk4
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

    # Bank metadata
    d += _name("Bank")
    d += _inline(b"\x00\x02" + b"\x00" * 9)

    d += _name("BankId")
    d += _inline(b"00000001")

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

    # NS1 — password info (empty password, KOD-encoded)
    _kod = koddecoder.new()
    plaintext = struct.pack("<LLL", 0x57, 0, 0) + b"\x00" * 8
    shift = 0xC2
    d += _name("NS1")
    d += _inline(bytes([0x02, shift]) + _kod.encode(shift, plaintext))

    # NS2
    d += _name("NS2")
    d += _inline(struct.pack("<L", 0x57))

    # Version — b"\x2d\x35" = ASCII "-5" (Cronos 5 marker; "-6" caused rejection in Cronos 5)
    d += _name("Version")
    d += _inline(b"\x2d\x35")

    return bytes(d)


# ── CroFile .dat / .tad writer ───────────────────────────────────────────────

class _CroFileWriter:
    """Build a pair of .dat + .tad CronosPRO files (v3, 32-bit, unencrypted)."""

    DAT_HEADER_SIZE = 19 + 0xE9  # 252 bytes

    def __init__(self, blocksize: int = 0x40):
        self.blocksize = blocksize
        self._records: list[bytes] = []

    def add_record(self, data: bytes):
        self._records.append(data)

    def build(self) -> tuple[bytes, bytes]:
        dat = bytearray()
        tad = bytearray()

        # .dat header: magic + unk + version + encoding + blocksize + 0xE9 padding
        dat += b"CroFile\x00"
        dat += struct.pack("<H", 0)        # unk
        dat += b"01.02"                    # version
        dat += struct.pack("<H", 0)        # encoding: plain, uncompressed
        dat += struct.pack("<H", self.blocksize)
        dat += b"\x00" * 0xE9             # padding bytes

        # .tad header: nrdeleted + firstdeleted
        tad += struct.pack("<LL", 0, 0)

        for rec in self._records:
            offset = len(dat)
            ln = len(rec)
            ln_flags = (0x80 << 24) | ln   # flags=0x80 means inline short record
            tad += struct.pack("<LLL", offset, ln_flags, 0)
            dat += rec

        return bytes(dat), bytes(tad)


# ── CroBank record encoder ────────────────────────────────────────────────────

_SAFE_CTRL = frozenset([0x09, 0x0a, 0x0d])  # TAB, LF, CR are OK in values

def _encode_bank_record(tableid: int, fields: list, row: dict) -> bytes:
    """
    Build a CroBank record: tableid byte + field values separated by 0x1E.
    fields is a list of field names (index 0 = Системный номер, skip it).
    Strip control bytes 0x00-0x1f (except TAB/LF/CR) to prevent
    0x1b (complex-record marker) and 0x1e (field separator) from corrupting reads.
    """
    parts = []
    for fname in fields[1:]:
        val = str(row.get(fname, "") or "")
        enc = val.encode('cp1251', errors='replace')
        enc = bytes(b for b in enc if b >= 0x20 or b in _SAFE_CTRL)
        parts.append(enc)
    return bytes([tableid]) + b"\x1e".join(parts)


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

    stru = _CroFileWriter(blocksize=0x0200)
    bank = _CroFileWriter(blocksize=0x0040)
    index = _CroFileWriter(blocksize=0x0400)  # empty index

    # We'll assign CroStru record numbers starting at 2
    # (rec #1 = DB definition, so tables start at rec #2)
    table_recnos = []

    # Also build an index of (table_id, tableid) for CroBank
    table_entries = []

    for t_idx, table in enumerate(tables):
        tableid = t_idx + 1
        tname   = table["name"]
        fnames  = table.get("fields", [])
        records = table.get("records", [])

        # Strip sysnum from incoming fields — we always add it ourselves
        user_fields = [f for f in fnames if f not in ("Системный номер", "__recno__")]

        # Infer field types from data sample
        sample_size = min(100, len(records))
        field_defs  = [_encode_field(0, "Системный номер", 0)]  # sysnum always first
        all_fields  = ["Системный номер"] + user_fields

        for i, fname in enumerate(user_fields, 1):
            samples = [r.get(fname, "") for r in records[:sample_size]]
            typ, maxval = _infer_type(samples)
            field_defs.append(_encode_field(i, fname, typ, maxval))

        # Encode TableDefinition and add to CroStru
        tdef_bytes = _encode_table(tableid, tname, field_defs)
        # CroStru record: 0x04 prefix + TableDefinition bytes
        stru_recno = len(stru._records) + 1  # will be 1-based after adding rec#1 later
        stru.add_record(b"\x04" + tdef_bytes)
        table_recnos.append(stru_recno)
        table_entries.append((tableid, all_fields, records))

        stats["tables"] += 1
        stats["records"] += len(records)

    # Build DB definition (CroStru rec #1) — must be first record
    # Adjust recnos: they should be 1-indexed; TableDefs are at positions 1..N
    # But we inserted them already at positions 0..N-1 in stru._records
    # DB def will be prepended → TableDef records shift to 2..N+1
    adjusted_recnos = [i + 2 for i in range(len(tables))]
    dbdef_bytes = _encode_dbdef(db_name, adjusted_recnos)

    # Prepend DB definition as the first record
    stru._records.insert(0, dbdef_bytes)

    # Write CroBank records
    for tableid, all_fields, records in table_entries:
        for rec_idx, row in enumerate(records):
            bank.add_record(_encode_bank_record(tableid, all_fields, row))

    # Build binary files
    stru_dat, stru_tad   = stru.build()
    bank_dat, bank_tad   = bank.build()
    index_dat, index_tad = index.build()

    # Write files — fsync ensures data reaches removable drives
    for fname, data in [
        ("CroStru.dat", stru_dat), ("CroStru.tad", stru_tad),
        ("CroBank.dat", bank_dat), ("CroBank.tad", bank_tad),
        ("CroIndex.dat", index_dat), ("CroIndex.tad", index_tad),
    ]:
        with open(os.path.join(output_dir, fname), "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

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
