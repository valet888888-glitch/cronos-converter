#!/usr/bin/env python3
"""
SQL/CSV/Cronos ↔ CronosPRO Конвертер v2.0
Двусторонняя конвертация: SQL/CSV → Cronos  и  Cronos → CSV/SQL

Запуск:
    python sql_to_cronos.py                          # GUI
    python sql_to_cronos.py dump.sql      ./out/     # SQL → Cronos
    python sql_to_cronos.py data.csv      ./out/     # CSV → Cronos
    python sql_to_cronos.py ./cronos_db/  ./out/ --export csv   # Cronos → CSV
    python sql_to_cronos.py ./cronos_db/  ./out/ --export sql   # Cronos → SQL

Требования: Python 3.7+, только стандартная библиотека.
"""

import os, sys, re, struct, csv, io, time, threading, argparse
from tkinter import (Tk, ttk, filedialog, messagebox, scrolledtext,
                     StringVar, IntVar, BooleanVar, Frame, Label, Entry,
                     Button, LabelFrame, Checkbutton, Radiobutton, END,
                     DISABLED, NORMAL, LEFT, RIGHT, BOTH, X, W)

# ═══════════════════════════════════════════════════════════════════
#  KOD-таблица (встроена из crodump/koddecoder.py, MIT licence)
# ═══════════════════════════════════════════════════════════════════

_KOD_TABLE = [
    0x08,0x63,0x81,0x38,0xA3,0x6B,0x82,0xA6,0x18,0x0D,0xAC,0xD5,0xFE,0xBE,0x15,0xF6,
    0xA5,0x36,0x76,0xE2,0x2D,0x41,0xB5,0x12,0x4B,0xD8,0x3C,0x56,0x34,0x46,0x4F,0xA4,
    0xD0,0x01,0x8B,0x60,0x0F,0x70,0x57,0x3E,0x06,0x67,0x02,0x7A,0xF8,0x8C,0x80,0xE8,
    0xC3,0xFD,0x0A,0x3A,0xA7,0x73,0xB0,0x4D,0x99,0xA2,0xF1,0xFB,0x5A,0xC7,0xC2,0x17,
    0x96,0x71,0xBA,0x2A,0xA9,0x9A,0xF3,0x87,0xEA,0x8E,0x09,0x9E,0xB9,0x47,0xD4,0x97,
    0xE4,0xB3,0xBC,0x58,0x53,0x5F,0x2E,0x21,0xD1,0x1A,0xEE,0x2C,0x64,0x95,0xF2,0xB8,
    0xC6,0x33,0x8D,0x2B,0x1F,0xF7,0x25,0xAD,0xFF,0x7F,0x39,0xA8,0xBF,0x6A,0x91,0x79,
    0xED,0x20,0x7B,0xA1,0xBB,0x45,0x69,0xCD,0xDC,0xE7,0x31,0xAA,0xF0,0x65,0xD7,0xA0,
    0x32,0x93,0xB1,0x24,0xD6,0x5B,0x9F,0x27,0x42,0x85,0x07,0x44,0x3F,0xB4,0x11,0x68,
    0x5E,0x49,0x29,0x13,0x94,0xE6,0x1B,0xE1,0x7D,0xC8,0x2F,0xFA,0x78,0x1D,0xE3,0xDE,
    0x50,0x4E,0x89,0xB6,0x30,0x48,0x0C,0x10,0x05,0x43,0xCE,0xD3,0x61,0x51,0x83,0xDA,
    0x77,0x6F,0x92,0x9D,0x74,0x7C,0x04,0x88,0x86,0x55,0xCA,0xF4,0xC1,0x62,0x0E,0x28,
    0xB7,0x0B,0xC0,0xF5,0xCF,0x35,0xC5,0x4C,0x16,0xE0,0x98,0x00,0x9B,0xD9,0xAE,0x03,
    0xAF,0xEC,0xC9,0xDB,0x6D,0x3B,0x26,0x75,0x3D,0xBD,0xB2,0x4A,0x5D,0x6C,0x72,0x40,
    0x7E,0xAB,0x59,0x52,0x54,0x9C,0xD2,0xE9,0xEF,0xDD,0x37,0x1E,0x8F,0xCB,0x8A,0x90,
    0xFC,0x84,0xE5,0xF9,0x14,0x19,0xDF,0x6E,0x23,0xC4,0x66,0xEB,0xCC,0x22,0x1C,0x5C,
]

def _kod_encode(shift: int, data: bytes) -> bytes:
    inv = [0] * 256
    for i, x in enumerate(_KOD_TABLE):
        inv[x] = i
    return bytes(inv[(b + i + shift) % 256] for i, b in enumerate(data))


# ═══════════════════════════════════════════════════════════════════
#  Определение кодировки
# ═══════════════════════════════════════════════════════════════════

_SQL_CHARSET_MAP = {
    'utf8mb4': 'utf-8', 'utf8': 'utf-8', 'utf-8': 'utf-8',
    'cp1251': 'cp1251', 'win1251': 'cp1251', 'windows1251': 'cp1251',
    'windows-1251': 'cp1251', '1251': 'cp1251',
    'koi8r': 'koi8-r', 'koi8-r': 'koi8-r',
    'latin1': 'latin-1', 'latin-1': 'latin-1', 'iso88591': 'latin-1',
}

def detect_encoding(path: str) -> str:
    with open(path, 'rb') as f:
        raw = f.read(65536)
    if raw.startswith(b'\xef\xbb\xbf'):  return 'utf-8-sig'
    if raw.startswith(b'\xff\xfe'):       return 'utf-16-le'
    for pattern in (
        rb'SET\s+NAMES\s+([a-zA-Z0-9_-]+)',
        rb'character[_\s]set[_\s]client\s*=\s*([a-zA-Z0-9_-]+)',
    ):
        m = re.search(pattern, raw[:4096], re.I)
        if m:
            declared = m.group(1).decode('ascii', 'ignore').lower().replace('-','').replace('_','')
            for key, enc in _SQL_CHARSET_MAP.items():
                if declared.startswith(key.replace('-','').replace('_','')):
                    return enc
    try:
        raw.decode('utf-8'); return 'utf-8'
    except UnicodeDecodeError:
        pass
    cp1251_hits = sum(1 for b in raw if 0xC0 <= b <= 0xFF)
    koi8_hits   = sum(1 for b in raw if 0xE0 <= b <= 0xFF)
    return 'cp1251' if cp1251_hits >= koi8_hits else 'koi8-r'


# ═══════════════════════════════════════════════════════════════════
#  SQL-парсер
# ═══════════════════════════════════════════════════════════════════

def parse_sql(path: str, progress_cb=None) -> list:
    encoding  = detect_encoding(path)
    file_size = os.path.getsize(path)

    re_create = re.compile(r'CREATE\s+TABLE\s+[`"]?(\w+)[`"]?', re.I)
    re_col    = re.compile(r'^\s*[`"](\w+)[`"]\s+\w', re.I | re.M)
    re_insert = re.compile(
        r'INSERT\s+INTO\s+[`"]?(\w+)[`"]?\s*(?:\(([^)]+)\))?\s*VALUES\s*(.*)',
        re.I | re.S)
    re_row    = re.compile(r'\(([^)]*(?:\([^)]*\)[^)]*)*)\)')

    tables: dict = {}
    current_table = None
    current_cols  = []
    bytes_read    = 0

    with open(path, encoding=encoding, errors='replace') as f:
        buf = ''
        for line in f:
            bytes_read += len(line.encode(encoding, errors='replace'))
            buf += line
            if not buf.rstrip().endswith(';'):
                continue
            stmt = buf.strip(); buf = ''
            if progress_cb:
                progress_cb(bytes_read, file_size)
            m = re_create.search(stmt)
            if m:
                current_table = m.group(1)
                current_cols  = re_col.findall(stmt)
                if current_table not in tables:
                    tables[current_table] = {"name": current_table,
                                             "fields": current_cols[:], "records": []}
                elif not tables[current_table]["fields"]:
                    tables[current_table]["fields"] = current_cols[:]
                continue
            m = re_insert.search(stmt)
            if not m:
                continue
            tbl = m.group(1); col_str = m.group(2); vals_str = m.group(3)
            if col_str:
                cols = [c.strip().strip('`"') for c in col_str.split(',')]
            elif tbl == current_table and current_cols:
                cols = current_cols
            elif tbl in tables and tables[tbl]["fields"]:
                cols = tables[tbl]["fields"]
            else:
                cols = []
            if tbl not in tables:
                tables[tbl] = {"name": tbl, "fields": cols[:], "records": []}
            for row_m in re_row.finditer(vals_str):
                vals = _split_values(row_m.group(1))
                row = ({cols[i]: vals[i] if i < len(vals) else ''
                        for i in range(len(cols))} if cols
                       else {f"col{i}": v for i, v in enumerate(vals)})
                tables[tbl]["records"].append(row)
                if not tables[tbl]["fields"] and row:
                    tables[tbl]["fields"] = list(row.keys())

    return [t for t in tables.values() if t["records"]]


_SQL_UNESCAPE = str.maketrans({'n':'\n','r':'\r','t':'\t','0':'\0','Z':'\x1a','b':'\b'})

def _split_values(raw: str) -> list:
    vals = []; cur = []; in_q = False; q_ch = ''; i = 0
    while i < len(raw):
        ch = raw[i]
        if in_q and ch == '\\' and i + 1 < len(raw):
            nxt = raw[i+1]
            cur.append(nxt if nxt in (q_ch, '\\') else
                       _SQL_UNESCAPE.get(nxt, nxt) if len(nxt) == 1 else nxt)
            i += 2; continue
        if not in_q and ch in ('"', "'"):
            in_q = True; q_ch = ch; i += 1; continue
        if in_q and ch == q_ch:
            in_q = False; i += 1; continue
        if not in_q and ch == ',':
            vals.append(''.join(cur).strip()); cur = []; i += 1; continue
        cur.append(ch); i += 1
    vals.append(''.join(cur).strip())
    return ['' if v.upper().rstrip() in ('NULL',) else v for v in vals]


# ═══════════════════════════════════════════════════════════════════
#  CSV-парсер
# ═══════════════════════════════════════════════════════════════════

def parse_csv(path: str, progress_cb=None) -> list:
    encoding   = detect_encoding(path)
    file_size  = os.path.getsize(path)
    table_name = os.path.splitext(os.path.basename(path))[0]

    with open(path, encoding=encoding, errors='replace') as fh:
        sample = fh.read(8192)
    try:
        dialect   = csv.Sniffer().sniff(sample)
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ','

    records = []; fields = []
    with open(path, encoding=encoding, errors='replace', newline='') as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        fields = list(reader.fieldnames or [])
        for i, row in enumerate(reader):
            records.append(dict(row))
            if progress_cb and i % 10000 == 0:
                progress_cb(fh.tell(), file_size)

    return [{"name": table_name, "fields": fields, "records": records}]


# ═══════════════════════════════════════════════════════════════════
#  Встроенный Cronos-читатель (без внешних зависимостей)
# ═══════════════════════════════════════════════════════════════════

def _cro_read_name(data: bytes, pos: int):
    """Читает length-prefixed cp1251 строку. Возвращает (str, new_pos)."""
    if pos >= len(data):
        return '', pos
    length = data[pos]; pos += 1
    name = data[pos:pos+length].decode('cp1251', errors='replace')
    return name, pos + length


def _read_dat_records(dat_path: str) -> list:
    """Читает все записи из пары .dat/.tad файлов CronosPRO."""
    tad_path = os.path.splitext(dat_path)[0] + '.tad'
    if not os.path.exists(dat_path) or not os.path.exists(tad_path):
        raise FileNotFoundError(f"Файлы не найдены: {dat_path}")
    with open(dat_path, 'rb') as f:
        dat = f.read()
    with open(tad_path, 'rb') as f:
        tad = f.read()
    if not dat.startswith(b'CroFile\x00'):
        raise ValueError(f"Не CroFile формат: {dat_path}")

    records = []
    pos = 8  # пропустить TAD-заголовок (nrdeleted + firstdeleted)
    while pos + 12 <= len(tad):
        offset, len_flags, _ = struct.unpack_from('<LLL', tad, pos)
        pos += 12
        if offset == 0 and len_flags == 0:
            continue
        flag     = (len_flags >> 24) & 0xFF
        data_len = len_flags & 0x00FFFFFF
        if flag == 0xFF:  # удалённая запись
            continue
        if offset + data_len <= len(dat):
            records.append(dat[offset:offset + data_len])
    return records


def _parse_table_def(rec: bytes):
    """Разбирает TableDefinition из записи CroStru (0x04 prefix).
    Возвращает dict или None."""
    if not rec or rec[0] != 0x04:
        return None
    try:
        pos = 1
        pos += 2                          # unk1
        version = rec[pos]; pos += 1
        if version > 1:
            pos += 1                      # pad (version > 1)
        unk2 = rec[pos]; pos += 1
        pos += 1                          # unk3
        if unk2 > 5:
            pos += 4                      # extra_dword
        pos += 4                          # unk4
        tableid = struct.unpack_from('<L', rec, pos)[0]; pos += 4
        name,   pos = _cro_read_name(rec, pos)
        _abbrev, pos = _cro_read_name(rec, pos)
        pos += 4                          # unk7
        nrfields = struct.unpack_from('<L', rec, pos)[0]; pos += 4

        fields = []
        for _ in range(nrfields):
            if pos + 2 > len(rec):
                break
            flen  = struct.unpack_from('<H', rec, pos)[0]; pos += 2
            fdata = rec[pos:pos+flen];     pos += flen
            if len(fdata) < 7:
                continue
            ftyp  = struct.unpack_from('<H', fdata, 0)[0]
            fname, _ = _cro_read_name(fdata, 6)
            fields.append((fname, ftyp))

        return {"tableid": tableid, "name": name, "fields": fields}
    except Exception:
        return None


def parse_cronos(db_dir: str, progress_cb=None) -> list:
    """
    Читает базу CronosPRO из папки.
    Возвращает [{"name", "fields", "records"}] — как parse_sql/parse_csv.
    """
    files = {f.lower(): f for f in os.listdir(db_dir)}
    stru_name = files.get('crostru.dat')
    bank_name = files.get('crobank.dat')
    if not stru_name:
        raise FileNotFoundError("CroStru.dat не найден в " + db_dir)

    stru_records = _read_dat_records(os.path.join(db_dir, stru_name))

    # Разобрать схему
    schema = {}  # tableid → {name, fields: [(fname, ftyp)]}
    for rec in stru_records:
        td = _parse_table_def(rec)
        if td and td["name"] not in ("Files",):
            schema[td["tableid"]] = td

    if not bank_name:
        return [{"name": v["name"], "fields": [f[0] for f in v["fields"][1:]],
                 "records": []} for v in schema.values()]

    bank_records = _read_dat_records(os.path.join(db_dir, bank_name))
    total_bank   = len(bank_records)

    # Сгруппировать bank-записи по tableid
    by_table = {}
    for i, rec in enumerate(bank_records):
        if not rec:
            continue
        tid = rec[0]
        by_table.setdefault(tid, []).append(rec[1:])
        if progress_cb and i % 50000 == 0:
            progress_cb(i, total_bank)

    result = []
    for tableid, tdef in sorted(schema.items()):
        tname        = tdef["name"]
        all_fields   = [f[0] for f in tdef["fields"]]
        # Первое поле — "Системный номер", значения которого не хранятся в CroBank
        user_fields  = all_fields[1:] if len(all_fields) > 1 else all_fields

        records = []
        for raw in by_table.get(tableid, []):
            parts = raw.split(b'\x1e')
            row = {}
            for i, fname in enumerate(user_fields):
                val_bytes = parts[i] if i < len(parts) else b''
                try:
                    row[fname] = val_bytes.decode('cp1251')
                except Exception:
                    row[fname] = val_bytes.decode('latin-1', errors='replace')
            records.append(row)

        result.append({"name": tname, "fields": user_fields, "records": records})

    if progress_cb:
        progress_cb(total_bank, total_bank)
    return result


# ═══════════════════════════════════════════════════════════════════
#  Экспорт в CSV и SQL
# ═══════════════════════════════════════════════════════════════════

def tables_to_csv(tables: list, output_dir: str, progress_cb=None) -> list:
    """Пишет по одному CSV-файлу на таблицу. Возвращает список путей."""
    os.makedirs(output_dir, exist_ok=True)
    written = []
    for table in tables:
        safe  = re.sub(r'[^\w\-_]', '_', table["name"])
        path  = os.path.join(output_dir, safe + '.csv')
        flds  = table["fields"]
        recs  = table["records"]
        with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.DictWriter(fh, fieldnames=flds, extrasaction='ignore')
            w.writeheader()
            for i, row in enumerate(recs):
                w.writerow(row)
                if progress_cb and i % 50000 == 0:
                    progress_cb(i, len(recs))
        written.append(path)
    return written


def tables_to_sql(tables: list, output_path: str,
                  db_name: str = "export", progress_cb=None) -> int:
    """Пишет MySQL SQL-дамп. Возвращает общее количество записей."""
    total = 0
    with open(output_path, 'w', encoding='utf-8') as fh:
        fh.write(f"-- SQL↔Cronos Converter  db={db_name}\n")
        fh.write("SET NAMES utf8mb4;\n\n")
        for table in tables:
            tname = table["name"]
            flds  = table["fields"]
            recs  = table["records"]
            safe_t = tname.replace('`', '``')
            fh.write(f"DROP TABLE IF EXISTS `{safe_t}`;\n")
            col_lines  = [f"  `{f.replace('`','``')}` text" for f in flds]
            fh.write(f"CREATE TABLE `{safe_t}` (\n")
            fh.write(",\n".join(col_lines))
            fh.write("\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n")
            if recs:
                col_part = ", ".join(f"`{f.replace('`','``')}`" for f in flds)
                fh.write(f"INSERT INTO `{safe_t}` ({col_part}) VALUES\n")
                rows_sql = []
                for i, rec in enumerate(recs):
                    vals = []
                    for f in flds:
                        v = str(rec.get(f, '') or '')
                        v = v.replace('\\','\\\\').replace("'","\\'") \
                             .replace('\n','\\n').replace('\r','\\r')
                        vals.append(f"'{v}'")
                    rows_sql.append(f"({', '.join(vals)})")
                    total += 1
                    if progress_cb and i % 50000 == 0:
                        progress_cb(i, len(recs))
                fh.write(',\n'.join(rows_sql) + ';\n\n')
    return total


# ═══════════════════════════════════════════════════════════════════
#  Cronos-writer (встроен)
# ═══════════════════════════════════════════════════════════════════

def _cro_name(s: str) -> bytes:
    b = s.encode('cp1251', errors='replace')
    return bytes([min(len(b), 255)]) + b[:255]

def _cro_inline(data: bytes) -> bytes:
    return struct.pack("<L", 0x80000000 | len(data)) + data

def _cro_ref(recno: int) -> bytes:
    return struct.pack("<L", recno)

def _infer_type(samples: list) -> tuple:
    non_empty = [str(v) for v in samples if v and str(v).strip()
                 and str(v).upper() != 'NULL']
    if not non_empty:
        return 2, 256
    if all(re.fullmatch(r'-?\d+', v.strip()) for v in non_empty):
        return 1, 20
    if (sum(1 for v in non_empty
            if re.fullmatch(r'\d{2,4}[-./]\d{1,2}[-./]\d{1,4}', v.strip()))
            / len(non_empty) > 0.8):
        return 4, 10
    maxlen = max(len(v) for v in non_empty)
    return (3, 65535) if maxlen > 500 else (2, max(maxlen + 50, 64))

def _enc_field(idx: int, name: str, typ: int, maxval: int = 256) -> bytes:
    d = bytearray()
    d += struct.pack("<H", typ)
    d += struct.pack("<L", idx)
    d += _cro_name(name)
    d += struct.pack("<L", 0)
    d += bytes([1 if typ else 0])
    if typ:
        d += struct.pack("<L", idx)
        d += struct.pack("<L", maxval)
        d += struct.pack("<L", 0x10019)
        d += b"\x00" * 13
    return bytes(d)

def _enc_table(tableid: int, name: str, field_defs: list) -> bytes:
    d = bytearray()
    d += struct.pack("<H", 0)
    d += bytes([3, 0, 9, 1])
    d += struct.pack("<L", 2)
    d += struct.pack("<L", 0)
    d += struct.pack("<L", tableid)
    d += _cro_name(name)
    d += _cro_name(name[:2])
    d += struct.pack("<L", 1)
    d += struct.pack("<L", len(field_defs))
    for fdef in field_defs:
        d += struct.pack("<H", len(fdef)) + fdef
    d += struct.pack("<L", 0)
    d += struct.pack("<L", 0)
    d += bytes([2])
    d += struct.pack("<L", 0)
    d += struct.pack("<L", 0)
    return bytes(d)

def _enc_dbdef(db_name: str, table_recnos: list) -> bytes:
    d = bytearray()
    d += bytes([0x03])
    d += _cro_name("Bank");       d += _cro_inline(b"\x00\x02" + b"\x00" * 9)
    d += _cro_name("BankId");     d += _cro_inline(b"00000001")
    d += _cro_name("BankName");   d += _cro_inline(db_name.encode('cp1251','replace'))
    files_def = _enc_table(0, "Files", [
        _enc_field(0, "Системный номер", 0),
        _enc_field(1, "Name", 2, 256),
    ])
    d += _cro_name("Base000");    d += _cro_inline(files_def)
    d += _cro_name("Formuls000"); d += _cro_inline(b"\x00" * 8)
    d += _cro_name("Formuls001"); d += _cro_inline(b"\x00" * 8)
    for i, recno in enumerate(table_recnos, 1):
        d += _cro_name(f"Base{i:03d}"); d += _cro_ref(recno)
    shift = 0xC2
    plain = struct.pack("<LLL", 0x57, 0, 0) + b"\x00" * 8
    d += _cro_name("NS1");    d += _cro_inline(bytes([0x02, shift]) + _kod_encode(shift, plain))
    d += _cro_name("NS2");    d += _cro_inline(struct.pack("<L", 0x57))
    d += _cro_name("Version"); d += _cro_inline(b"\x2d\x36")
    return bytes(d)

def _safe_cp1251(s: str) -> bytes:
    try:
        return s.encode('cp1251')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    _T = {
        'Қ':'К','қ':'к','Ғ':'Г','ғ':'г','Ұ':'У','ұ':'у','Ү':'У','ү':'у',
        'Ө':'О','ө':'о','Ң':'Н','ң':'н','Ә':'А','ә':'а','І':'И','і':'и',
        'Һ':'Х','һ':'х','Є':'Е','є':'е','Ї':'И','ї':'и',
        'Ё':'Е','ё':'е',
        '—':'-','–':'-','…':'...','«':'<<','»':'>>',
        '“':'"', '”':'"', '’':"'", ' ':' ', '­':'',
    }
    result = []
    for ch in s:
        try:
            result.append(ch.encode('cp1251'))
        except (UnicodeEncodeError, UnicodeDecodeError):
            result.append(_T.get(ch, '?').encode('cp1251', errors='replace'))
    return b''.join(result)

def _enc_bank_record(tableid: int, user_fields: list, row: dict) -> tuple:
    parts = []; lost = 0
    for f in user_fields:
        raw_val = str(row.get(f, '') or '')
        encoded = _safe_cp1251(raw_val)
        lost   += max(encoded.count(b'?') - raw_val.count('?'), 0)
        parts.append(encoded)
    return bytes([tableid]) + b"\x1e".join(parts), lost

class _CroWriter:
    def __init__(self, blocksize=0x40):
        self.blocksize = blocksize
        self._recs: list = []
    def add(self, data: bytes):
        self._recs.append(data)
    def build(self) -> tuple:
        dat = bytearray(); tad = bytearray()
        dat += b"CroFile\x00"
        dat += struct.pack("<H", 0)
        dat += b"01.02"
        dat += struct.pack("<H", 0)
        dat += struct.pack("<H", self.blocksize)
        dat += b"\x00" * 0xE9
        tad += struct.pack("<LL", 0, 0)
        for rec in self._recs:
            tad += struct.pack("<LLL", len(dat), (0x80 << 24) | len(rec), 0)
            dat += rec
        return bytes(dat), bytes(tad)

def write_cronos(tables: list, output_dir: str,
                 db_name: str = "export", progress_cb=None) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    stru  = _CroWriter(0x0200)
    bank  = _CroWriter(0x0040)
    index = _CroWriter(0x0400)
    table_entries = []
    total = sum(len(t.get("records",[])) for t in tables)
    done = 0; lost_chars = 0

    for t_idx, table in enumerate(tables):
        tableid    = t_idx + 1
        tname      = table["name"]
        all_fnames = table.get("fields", [])
        records    = table.get("records", [])
        user_fields= [f for f in all_fnames if f not in ("Системный номер","__recno__")]
        sample     = min(100, len(records))
        fdefs      = [_enc_field(0, "Системный номер", 0)]
        for i, fname in enumerate(user_fields, 1):
            samples = [r.get(fname,"") for r in records[:sample]]
            typ, maxval = _infer_type(samples)
            fdefs.append(_enc_field(i, fname, typ, maxval))
        stru.add(b"\x04" + _enc_table(tableid, tname, fdefs))
        table_entries.append((tableid, user_fields, records))

    stru._recs.insert(0, _enc_dbdef(db_name, [i+2 for i in range(len(tables))]))

    for tableid, user_fields, records in table_entries:
        for row in records:
            rec_bytes, lc = _enc_bank_record(tableid, user_fields, row)
            bank.add(rec_bytes)
            lost_chars += lc; done += 1
            if progress_cb and done % 5000 == 0:
                progress_cb(done, total)

    if progress_cb:
        progress_cb(total, total)

    for prefix, writer in [("CroStru",stru),("CroBank",bank),("CroIndex",index)]:
        dat, tad = writer.build()
        open(os.path.join(output_dir, prefix+".dat"),"wb").write(dat)
        open(os.path.join(output_dir, prefix+".tad"),"wb").write(tad)

    result = {"tables": len(tables), "records": done}
    if lost_chars > 0:
        result["warning"] = (
            f"{lost_chars:,} символов заменены на '?' (emoji, казахские/украинские буквы).")
    return result


# ═══════════════════════════════════════════════════════════════════
#  Нормализация данных
# ═══════════════════════════════════════════════════════════════════

_RE_PHONE_FIELD = re.compile(
    r'phone|tel(?:efon)?|mob(?:ile)?|cell|сотов|телефон|тел\b|моб|phone_?num', re.I)
_RE_PASSPORT_FIELD = re.compile(
    r'passport|pasport|паспорт|пасп(?:орт)?|pass_n|docum(?:ent)?|doc_n', re.I)
_RE_PASSPORT_SERIES = re.compile(
    r'(?:pass(?:port)?|pasport|паспорт|пасп)[_\s]?(?:ser(?:ies?)?|seria|серия|сер)', re.I)
_RE_PASSPORT_NUMBER = re.compile(
    r'(?:pass(?:port)?|pasport|паспорт|пасп)[_\s]?(?:num(?:ber)?|nomer|no\b|номер|ном)', re.I)
_RE_LASTNAME  = re.compile(
    r'^(?:last_?name|surname|фамилия|фам(?:_|$)|lastname|family(?:_name)?|familiya|fam)$', re.I)
_RE_FIRSTNAME = re.compile(
    r'^(?:first_?name|given_?name|имя|firstname|fn$|givenname|name$|ima$)$', re.I)
_RE_MIDDLENAME= re.compile(
    r'^(?:middle_?name|patronymic|отчество|отч(?:_|$)|middlename|patronym(?:a)?|patron|otchestvo|otch$)$', re.I)

# Адрес
_RE_ADDR_FULL   = re.compile(
    r'^(?:address|adres|addr(?:ess)?|адрес|full_?addr|home_?addr|'
    r'адр(?:ес)?|reg_?addr|mail_?addr|место_?жит|прожив\w*)$', re.I)
_RE_ADDR_ZIP    = re.compile(
    r'^(?:zip|postal_?code?|postcode|index|индекс|zip_?code?|post_?index)$', re.I)
_RE_ADDR_REGION = re.compile(
    r'^(?:region|регион|oblast|область|province|кра[йи]|krai|kraj|субъект)$', re.I)
_RE_ADDR_CITY   = re.compile(
    r'^(?:city|город|gorod|town|нп|locality|settlement|населен\w*)$', re.I)
_RE_ADDR_STREET = re.compile(
    r'^(?:street|улица|ul(?:ica)?|ulitsa|street_?name|ул(?:_|$))$', re.I)
_RE_ADDR_HOUSE  = re.compile(
    r'^(?:house|дом|dom|house_?num|bld(?:g)?|building|house_?number|дом_?номер)$', re.I)
_RE_ADDR_FLAT   = re.compile(
    r'^(?:flat|квартира|apartment|apt|kv|room|flat_?num|кв(?:_|$))$', re.I)


def normalize_phone(val: str) -> str:
    if not val or not val.strip():
        return val
    digits = re.sub(r'\D', '', val)
    if len(digits) == 11 and digits[0] == '8':
        digits = '7' + digits[1:]
    elif len(digits) == 10 and digits[0] == '9':
        digits = '7' + digits
    return digits if len(digits) == 11 and digits[0] == '7' else val


def normalize_passport(val: str) -> str:
    if not val or not val.strip():
        return val
    digits = re.sub(r'\D', '', val)
    return digits[:4] + ' ' + digits[4:] if len(digits) == 10 else val


def normalize_tables(tables: list, log_cb=None,
                     do_phone=True, do_passport=True,
                     do_fio=True, do_address=True) -> list:
    """
    Нормализует все таблицы:
    • Телефоны → 79XXXXXXXXX
    • Паспорта → XXXX XXXXXX  (объединяет серию+номер если раздельно)
    • ФИО      → единое поле из Фамилии+Имени+Отчества
    • Адрес    → единое поле из Индекса+Региона+Города+Улицы+Дома+Квартиры
    """
    for table in tables:
        fields  = table.get("fields", [])
        records = table.get("records", [])
        tname   = table.get("name", "?")
        if not records:
            continue

        # ── Телефоны ──────────────────────────────────────────────
        phone_fields = [f for f in fields if _RE_PHONE_FIELD.search(f)] if do_phone else []

        # ── Паспорт ───────────────────────────────────────────────
        pass_single = [f for f in fields
                       if _RE_PASSPORT_FIELD.search(f)
                       and not _RE_PASSPORT_SERIES.search(f)
                       and not _RE_PASSPORT_NUMBER.search(f)] if do_passport else []
        pass_series = (next((f for f in fields if _RE_PASSPORT_SERIES.search(f)), None)
                       if do_passport else None)
        pass_number = (next((f for f in fields if _RE_PASSPORT_NUMBER.search(f)), None)
                       if do_passport else None)
        combine_pass = pass_series and pass_number and 'Паспорт' not in fields

        # ── ФИО ───────────────────────────────────────────────────
        f_last  = (next((f for f in fields if _RE_LASTNAME.match(f)),   None) if do_fio else None)
        f_first = (next((f for f in fields if _RE_FIRSTNAME.match(f)),  None) if do_fio else None)
        f_mid   = (next((f for f in fields if _RE_MIDDLENAME.match(f)), None) if do_fio else None)
        has_fio_parts = bool(f_last or f_first or f_mid)
        has_fio_field = any(f in ('ФИО','FIO','fio','fullname','full_name') for f in fields)

        # ── Адрес ─────────────────────────────────────────────────
        f_zip    = (next((f for f in fields if _RE_ADDR_ZIP.match(f)),    None) if do_address else None)
        f_region = (next((f for f in fields if _RE_ADDR_REGION.match(f)), None) if do_address else None)
        f_city   = (next((f for f in fields if _RE_ADDR_CITY.match(f)),   None) if do_address else None)
        f_street = (next((f for f in fields if _RE_ADDR_STREET.match(f)), None) if do_address else None)
        f_house  = (next((f for f in fields if _RE_ADDR_HOUSE.match(f)),  None) if do_address else None)
        f_flat   = (next((f for f in fields if _RE_ADDR_FLAT.match(f)),   None) if do_address else None)
        addr_parts_fields = [f for f in (f_zip, f_region, f_city, f_street, f_house, f_flat) if f]
        has_addr_parts = len(addr_parts_fields) >= 2
        has_addr_field = any(_RE_ADDR_FULL.match(f) for f in fields)

        phone_cnt = pass_cnt = fio_cnt = addr_cnt = 0

        for rec in records:
            # Телефоны
            for pf in phone_fields:
                v = rec.get(pf, '')
                if v:
                    n = normalize_phone(str(v))
                    if n != str(v):
                        rec[pf] = n; phone_cnt += 1

            # Паспорт (единое поле)
            for pf in pass_single:
                v = rec.get(pf, '')
                if v:
                    n = normalize_passport(str(v))
                    if n != str(v):
                        rec[pf] = n; pass_cnt += 1

            # Паспорт (серия + номер → объединить)
            if combine_pass:
                s = re.sub(r'\D','', str(rec.get(pass_series,'') or ''))
                n = re.sub(r'\D','', str(rec.get(pass_number, '') or ''))
                if s and n and len(s+n) == 10:
                    rec['Паспорт'] = s[:4] + ' ' + (s+n)[4:]; pass_cnt += 1

            # ФИО
            if has_fio_parts and not has_fio_field:
                parts = []
                for f in (f_last, f_first, f_mid):
                    if f:
                        v = str(rec.get(f,'') or '').strip()
                        if v: parts.append(v)
                fio_val = ' '.join(parts)
                if fio_val:
                    rec['ФИО'] = fio_val; fio_cnt += 1

            # Адрес
            if has_addr_parts and not has_addr_field:
                def _g(f): return str(rec.get(f,'') or '').strip() if f else ''
                parts = []
                if f_zip:    v = _g(f_zip);    v and parts.append(v)
                if f_region: v = _g(f_region); v and parts.append(v)
                if f_city:   v = _g(f_city);   v and parts.append(v)
                if f_street: v = _g(f_street); v and parts.append("ул. " + v)
                if f_house:  v = _g(f_house);  v and parts.append("д. " + v)
                if f_flat:   v = _g(f_flat);   v and parts.append("кв. " + v)
                addr_val = ', '.join(parts)
                if addr_val:
                    rec['Адрес'] = addr_val; addr_cnt += 1

        # Обновить список полей
        if combine_pass and pass_cnt > 0 and 'Паспорт' not in fields:
            at = fields.index(pass_series) if pass_series in fields else len(fields)
            fields.insert(at, 'Паспорт'); table["fields"] = fields

        if has_fio_parts and not has_fio_field and fio_cnt > 0:
            at = 0
            for i, f in enumerate(fields):
                if re.match(r'^(id|сис|sys|recno|__)', f, re.I): at = i + 1
            fields.insert(at, 'ФИО'); table["fields"] = fields

        if has_addr_parts and not has_addr_field and addr_cnt > 0:
            # Вставить после ФИО (или в начало)
            at = (fields.index('ФИО') + 1) if 'ФИО' in fields else 0
            for i, f in enumerate(fields):
                if re.match(r'^(id|сис|sys|recno|__)', f, re.I): at = i + 1
            if 'ФИО' in fields:
                at = fields.index('ФИО') + 1
            fields.insert(at, 'Адрес'); table["fields"] = fields

        if log_cb:
            msgs = []
            if phone_cnt  > 0: msgs.append(f"тел: {phone_cnt:,}")
            if pass_cnt   > 0: msgs.append(f"паспорт: {pass_cnt:,}")
            if fio_cnt    > 0:
                used = [p for p in (f_last, f_first, f_mid) if p]
                msgs.append(f"ФИО из [{'+'.join(used)}]: {fio_cnt:,}")
            if addr_cnt   > 0:
                msgs.append(f"Адрес из [{'+'.join(addr_parts_fields)}]: {addr_cnt:,}")
            if msgs:
                log_cb(f"  [{tname}] нормализация: {', '.join(msgs)}")

    return tables


# ═══════════════════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════════════════

class App(Tk):
    def __init__(self):
        super().__init__()
        self.title("SQL/CSV ↔ CronosPRO Конвертер v2.0")
        self.resizable(True, True)
        self.minsize(680, 620)
        self._build_ui()

    # ── Строительство интерфейса ────────────────────────────────────

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill=BOTH, expand=True, padx=6, pady=6)

        tab1 = Frame(nb); nb.add(tab1, text="  SQL/CSV → Cronos  ")
        tab2 = Frame(nb); nb.add(tab2, text="  Cronos → CSV/SQL  ")

        self._build_import_tab(tab1)
        self._build_export_tab(tab2)

    # ─── Таб 1: импорт ─────────────────────────────────────────────

    def _build_import_tab(self, parent):
        pad = dict(padx=8, pady=3)

        f1 = LabelFrame(parent, text=" Исходный файл (SQL или CSV) ")
        f1.pack(fill=X, **pad)
        self.src_var = StringVar()
        Entry(f1, textvariable=self.src_var, width=60).pack(
            side=LEFT, padx=6, pady=5, fill=X, expand=True)
        Button(f1, text="Обзор…", command=self._pick_src).pack(side=LEFT, padx=4)

        f2 = LabelFrame(parent, text=" Папка вывода ")
        f2.pack(fill=X, **pad)
        self.dst_var = StringVar()
        Entry(f2, textvariable=self.dst_var, width=60).pack(
            side=LEFT, padx=6, pady=5, fill=X, expand=True)
        Button(f2, text="Обзор…", command=self._pick_dst).pack(side=LEFT, padx=4)

        fp = LabelFrame(parent, text=" Параметры ")
        fp.pack(fill=X, **pad)
        Label(fp, text="Имя базы:").grid(row=0, column=0, sticky=W, padx=6, pady=3)
        self.name_var = StringVar(value="export")
        Entry(fp, textvariable=self.name_var, width=28).grid(row=0, column=1, sticky=W)
        Label(fp, text="Лимит записей (0=все):").grid(row=1, column=0, sticky=W, padx=6, pady=3)
        self.limit_var = StringVar(value="0")
        Entry(fp, textvariable=self.limit_var, width=12).grid(row=1, column=1, sticky=W)

        fn = LabelFrame(parent, text=" Нормализация ")
        fn.pack(fill=X, **pad)
        self.norm_phone  = BooleanVar(value=True)
        self.norm_pass   = BooleanVar(value=True)
        self.norm_fio    = BooleanVar(value=True)
        self.norm_addr   = BooleanVar(value=True)
        Checkbutton(fn, text="Телефоны → 79XXXXXXXXX",    variable=self.norm_phone).grid(
            row=0, column=0, sticky=W, padx=8, pady=2)
        Checkbutton(fn, text="Паспорт → XXXX XXXXXX",      variable=self.norm_pass).grid(
            row=0, column=1, sticky=W, padx=8, pady=2)
        Checkbutton(fn, text="Объединить ФИО",              variable=self.norm_fio).grid(
            row=1, column=0, sticky=W, padx=8, pady=2)
        Checkbutton(fn, text="Объединить Адрес",            variable=self.norm_addr).grid(
            row=1, column=1, sticky=W, padx=8, pady=2)

        fpg = LabelFrame(parent, text=" Прогресс ")
        fpg.pack(fill=X, **pad)
        self.i_prog_var = IntVar()
        self.i_prog_bar = ttk.Progressbar(fpg, variable=self.i_prog_var, maximum=100)
        self.i_prog_bar.pack(fill=X, padx=6, pady=4)
        self.i_status_var = StringVar(value="Готов")
        Label(fpg, textvariable=self.i_status_var, anchor=W).pack(fill=X, padx=6)

        fl = LabelFrame(parent, text=" Лог ")
        fl.pack(fill=BOTH, expand=True, **pad)
        self.i_log = scrolledtext.ScrolledText(fl, height=9, state=DISABLED,
                                               font=("Consolas", 9))
        self.i_log.pack(fill=BOTH, expand=True, padx=4, pady=4)

        bf = Frame(parent); bf.pack(fill=X, padx=8, pady=6)
        self.i_btn = Button(bf, text="▶  Конвертировать в Cronos",
                            command=self._start_import,
                            bg='#1d4ed8', fg='white',
                            font=('', 10, 'bold'), padx=12, pady=5)
        self.i_btn.pack(side=LEFT)
        Button(bf, text="Открыть папку", command=self._open_dst_import,
               padx=8).pack(side=LEFT, padx=6)
        Button(bf, text="Выход", command=self.destroy, padx=8).pack(side=RIGHT)

    # ─── Таб 2: экспорт ────────────────────────────────────────────

    def _build_export_tab(self, parent):
        pad = dict(padx=8, pady=3)

        f1 = LabelFrame(parent, text=" Папка с базой Cronos (содержит CroBank.dat, CroStru.dat) ")
        f1.pack(fill=X, **pad)
        self.cro_src_var = StringVar()
        Entry(f1, textvariable=self.cro_src_var, width=60).pack(
            side=LEFT, padx=6, pady=5, fill=X, expand=True)
        Button(f1, text="Обзор…", command=self._pick_cro_src).pack(side=LEFT, padx=4)

        f2 = LabelFrame(parent, text=" Папка/файл вывода ")
        f2.pack(fill=X, **pad)
        self.cro_dst_var = StringVar()
        Entry(f2, textvariable=self.cro_dst_var, width=60).pack(
            side=LEFT, padx=6, pady=5, fill=X, expand=True)
        Button(f2, text="Обзор…", command=self._pick_cro_dst).pack(side=LEFT, padx=4)

        ff = LabelFrame(parent, text=" Формат вывода ")
        ff.pack(fill=X, **pad)
        self.export_fmt = StringVar(value="csv")
        Radiobutton(ff, text="CSV (по одному файлу на таблицу)",
                    variable=self.export_fmt, value="csv").pack(
            anchor=W, padx=10, pady=3)
        Radiobutton(ff, text="SQL (MySQL INSERT-дамп)",
                    variable=self.export_fmt, value="sql").pack(
            anchor=W, padx=10, pady=3)

        fpg = LabelFrame(parent, text=" Прогресс ")
        fpg.pack(fill=X, **pad)
        self.e_prog_var = IntVar()
        self.e_prog_bar = ttk.Progressbar(fpg, variable=self.e_prog_var, maximum=100)
        self.e_prog_bar.pack(fill=X, padx=6, pady=4)
        self.e_status_var = StringVar(value="Готов")
        Label(fpg, textvariable=self.e_status_var, anchor=W).pack(fill=X, padx=6)

        fl = LabelFrame(parent, text=" Лог ")
        fl.pack(fill=BOTH, expand=True, **pad)
        self.e_log = scrolledtext.ScrolledText(fl, height=9, state=DISABLED,
                                               font=("Consolas", 9))
        self.e_log.pack(fill=BOTH, expand=True, padx=4, pady=4)

        bf = Frame(parent); bf.pack(fill=X, padx=8, pady=6)
        self.e_btn = Button(bf, text="▶  Экспортировать из Cronos",
                            command=self._start_export,
                            bg='#15803d', fg='white',
                            font=('', 10, 'bold'), padx=12, pady=5)
        self.e_btn.pack(side=LEFT)
        Button(bf, text="Открыть папку", command=self._open_dst_export,
               padx=8).pack(side=LEFT, padx=6)
        Button(bf, text="Выход", command=self.destroy, padx=8).pack(side=RIGHT)

    # ── Helpers ─────────────────────────────────────────────────────

    def _pick_src(self):
        p = filedialog.askopenfilename(
            title="Исходный файл",
            filetypes=[("SQL/CSV files","*.sql *.csv"),("All","*.*")])
        if p:
            self.src_var.set(p)
            base = os.path.splitext(os.path.basename(p))[0]
            if self.name_var.get() in ("export", ""):
                self.name_var.set(base)
            if not self.dst_var.get():
                self.dst_var.set(os.path.join(os.path.dirname(p), base+"_cronos"))

    def _pick_dst(self):
        p = filedialog.askdirectory(title="Папка вывода Cronos")
        if p: self.dst_var.set(p)

    def _pick_cro_src(self):
        p = filedialog.askdirectory(title="Папка с базой Cronos")
        if p:
            self.cro_src_var.set(p)
            if not self.cro_dst_var.get():
                self.cro_dst_var.set(p + "_export")

    def _pick_cro_dst(self):
        fmt = self.export_fmt.get()
        if fmt == "sql":
            p = filedialog.asksaveasfilename(
                title="Сохранить SQL-файл", defaultextension=".sql",
                filetypes=[("SQL","*.sql"),("All","*.*")])
        else:
            p = filedialog.askdirectory(title="Папка для CSV-файлов")
        if p: self.cro_dst_var.set(p)

    def _open_dst_import(self):
        d = self.dst_var.get()
        if d and os.path.isdir(d):
            os.startfile(d) if sys.platform=='win32' else os.system(f'open "{d}"')

    def _open_dst_export(self):
        d = self.cro_dst_var.get()
        target = os.path.dirname(d) if os.path.isfile(d) else d
        if target and os.path.isdir(target):
            os.startfile(target) if sys.platform=='win32' else os.system(f'open "{target}"')

    def _ilog(self, msg: str):
        self.i_log.configure(state=NORMAL)
        self.i_log.insert(END, msg+"\n"); self.i_log.see(END)
        self.i_log.configure(state=DISABLED)

    def _elog(self, msg: str):
        self.e_log.configure(state=NORMAL)
        self.e_log.insert(END, msg+"\n"); self.e_log.see(END)
        self.e_log.configure(state=DISABLED)

    def _i_status(self, msg, pct=None):
        self.i_status_var.set(msg)
        if pct is not None: self.i_prog_var.set(pct)
        self.update_idletasks()

    def _e_status(self, msg, pct=None):
        self.e_status_var.set(msg)
        if pct is not None: self.e_prog_var.set(pct)
        self.update_idletasks()

    # ── Запуск импорта ──────────────────────────────────────────────

    def _start_import(self):
        src  = self.src_var.get().strip()
        dst  = self.dst_var.get().strip()
        name = self.name_var.get().strip() or "export"
        try:    limit = int(self.limit_var.get() or 0)
        except: limit = 0
        if not src or not os.path.isfile(src):
            messagebox.showerror("Ошибка", "Укажите корректный SQL или CSV файл"); return
        if not dst:
            messagebox.showerror("Ошибка", "Укажите папку вывода"); return
        self.i_btn.config(state=DISABLED)
        self.i_log.configure(state=NORMAL)
        self.i_log.delete("1.0", END)
        self.i_log.configure(state=DISABLED)
        threading.Thread(target=self._run_import,
                         args=(src, dst, name, limit), daemon=True).start()

    def _run_import(self, src, dst, name, limit):
        t0 = time.time()
        try:
            size_mb = os.path.getsize(src)/1024/1024
            ext = os.path.splitext(src)[1].lower()
            self._ilog(f"Файл: {os.path.basename(src)} ({size_mb:.1f} MB)")
            self._ilog(f"Кодировка: {detect_encoding(src)}")
            self._i_status("Чтение файла...", 0)

            def prog(done, total):
                pct = int(done/max(total,1)*50)
                self._i_status(f"Парсинг: {done/1024/1024:.1f}/{total/1024/1024:.1f} MB", pct)

            if ext == '.csv':
                tables = parse_csv(src, progress_cb=prog)
            else:
                tables = parse_sql(src, progress_cb=prog)

            self._ilog(f"\nНайдено таблиц: {len(tables)}")
            for t in tables:
                self._ilog(f"  {t['name']:40s} {len(t['records']):>10,} записей")

            if limit > 0:
                for t in tables: t["records"] = t["records"][:limit]
                self._ilog(f"\nЛимит: {limit} записей/таблицу")

            self._ilog("\nНормализация данных...")
            tables = normalize_tables(
                tables, log_cb=self._ilog,
                do_phone=self.norm_phone.get(),
                do_passport=self.norm_pass.get(),
                do_fio=self.norm_fio.get(),
                do_address=self.norm_addr.get())

            total_recs = sum(len(t["records"]) for t in tables)
            self._ilog(f"\nИтого записей: {total_recs:,}")
            self._i_status("Запись Cronos...", 50)

            def wprog(done, total):
                pct = 50 + int(done/max(total,1)*50)
                self._i_status(f"Запись: {done:,}/{total:,}", pct)

            stats = write_cronos(tables, dst, db_name=name, progress_cb=wprog)

            elapsed = time.time()-t0
            self._ilog(f"\n✓ Готово за {elapsed:.1f} сек")
            self._ilog(f"Таблиц: {stats['tables']}, записей: {stats['records']:,}")
            if "warning" in stats:
                self._ilog(f"⚠  {stats['warning']}")
            self._ilog(f"Вывод: {dst}")
            for fn in ("CroStru.dat","CroStru.tad","CroBank.dat","CroBank.tad","CroIndex.dat","CroIndex.tad"):
                p = os.path.join(dst, fn)
                sz = os.path.getsize(p) if os.path.exists(p) else 0
                self._ilog(f"  {fn}  ({sz:,} bytes)")
            self._i_status(f"✓ Готово ({elapsed:.1f} сек)", 100)
            messagebox.showinfo("Готово",
                f"Конвертация завершена!\nТаблиц: {stats['tables']}\n"
                f"Записей: {stats['records']:,}\nПапка: {dst}")
        except Exception as e:
            import traceback
            self._ilog(f"\n✗ ОШИБКА: {e}\n{traceback.format_exc()}")
            self._i_status(f"Ошибка: {e}", 0)
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.i_btn.config(state=NORMAL)

    # ── Запуск экспорта ─────────────────────────────────────────────

    def _start_export(self):
        src = self.cro_src_var.get().strip()
        dst = self.cro_dst_var.get().strip()
        if not src or not os.path.isdir(src):
            messagebox.showerror("Ошибка", "Укажите папку с базой Cronos"); return
        if not dst:
            messagebox.showerror("Ошибка", "Укажите папку/файл вывода"); return
        self.e_btn.config(state=DISABLED)
        self.e_log.configure(state=NORMAL)
        self.e_log.delete("1.0", END)
        self.e_log.configure(state=DISABLED)
        threading.Thread(target=self._run_export,
                         args=(src, dst, self.export_fmt.get()), daemon=True).start()

    def _run_export(self, src, dst, fmt):
        t0 = time.time()
        try:
            self._elog(f"База: {src}")
            self._elog(f"Формат: {fmt.upper()}")
            self._e_status("Чтение Cronos...", 5)

            def rprog(done, total):
                pct = int(done/max(total,1)*60)
                self._e_status(f"Чтение: {done:,}/{total:,} записей", pct)

            tables = parse_cronos(src, progress_cb=rprog)

            self._elog(f"\nНайдено таблиц: {len(tables)}")
            total_recs = 0
            for t in tables:
                self._elog(f"  {t['name']:40s} {len(t['records']):>10,} записей")
                total_recs += len(t["records"])
            self._elog(f"\nВсего записей: {total_recs:,}")
            self._e_status(f"Запись {fmt.upper()}...", 65)

            def wprog(done, total):
                pct = 65 + int(done/max(total,1)*35)
                self._e_status(f"Запись: {done:,}/{total:,}", pct)

            if fmt == "csv":
                written = tables_to_csv(tables, dst, progress_cb=wprog)
                self._elog(f"\n✓ Записано {len(written)} CSV-файлов в {dst}")
                for p in written:
                    self._elog(f"  {os.path.basename(p)}  ({os.path.getsize(p):,} bytes)")
            else:
                db_name = os.path.basename(src.rstrip("/\\"))
                n = tables_to_sql(tables, dst, db_name=db_name, progress_cb=wprog)
                sz = os.path.getsize(dst)
                self._elog(f"\n✓ Записан SQL-файл: {dst}")
                self._elog(f"  Записей: {n:,}   Размер: {sz:,} bytes")

            elapsed = time.time()-t0
            self._e_status(f"✓ Готово ({elapsed:.1f} сек)", 100)
            messagebox.showinfo("Готово",
                f"Экспорт завершён!\nТаблиц: {len(tables)}\n"
                f"Записей: {total_recs:,}\nВремя: {elapsed:.1f} сек")
        except Exception as e:
            import traceback
            self._elog(f"\n✗ ОШИБКА: {e}\n{traceback.format_exc()}")
            self._e_status(f"Ошибка: {e}", 0)
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.e_btn.config(state=NORMAL)


# ═══════════════════════════════════════════════════════════════════
#  CLI режим
# ═══════════════════════════════════════════════════════════════════

def cli_main():
    ap = argparse.ArgumentParser(
        description=(
            "SQL/CSV → Cronos  или  Cronos → CSV/SQL\n"
            "  sql_to_cronos.py dump.sql   ./out/            # SQL → Cronos\n"
            "  sql_to_cronos.py data.csv   ./out/            # CSV → Cronos\n"
            "  sql_to_cronos.py ./cro_db/  ./out/ --export csv\n"
            "  sql_to_cronos.py ./cro_db/  dump.sql --export sql"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("source",     help="SQL-файл, CSV-файл или папка Cronos")
    ap.add_argument("output",     help="Папка вывода (Cronos/CSV) или SQL-файл")
    ap.add_argument("--name",     default="", help="Имя базы данных")
    ap.add_argument("--limit",    type=int, default=0, help="Лимит записей на таблицу")
    ap.add_argument("--export",   choices=["csv","sql"], default=None,
                    help="Cronos → CSV или SQL (если не указано — импорт в Cronos)")
    ap.add_argument("--no-phone", action="store_true", help="Не нормализовать телефоны")
    ap.add_argument("--no-pass",  action="store_true", help="Не нормализовать паспорта")
    ap.add_argument("--no-fio",   action="store_true", help="Не объединять ФИО")
    ap.add_argument("--no-addr",  action="store_true", help="Не объединять Адрес")
    args = ap.parse_args()

    # ── Cronos → CSV/SQL ─────────────────────────────────────────────
    if args.export:
        if not os.path.isdir(args.source):
            print(f"Не папка Cronos: {args.source}", file=sys.stderr); sys.exit(1)
        print(f"База Cronos: {args.source}")
        last = [0]
        def rprog(done, total):
            pct = int(done/max(total,1)*100)
            if pct != last[0]:
                print(f"\rЧтение: {pct}%  ", end='', flush=True); last[0] = pct
        tables = parse_cronos(args.source, progress_cb=rprog)
        print()
        print(f"Таблиц: {len(tables)}")
        for t in tables:
            print(f"  {t['name']:40s} {len(t['records']):>10,} записей")
        if args.limit > 0:
            for t in tables: t["records"] = t["records"][:args.limit]

        if args.export == "csv":
            written = tables_to_csv(tables, args.output)
            print(f"\nЗаписано {len(written)} CSV-файлов в {args.output}")
            for p in written:
                print(f"  {os.path.basename(p)}  ({os.path.getsize(p):,} bytes)")
        else:
            db_name = args.name or os.path.basename(args.source.rstrip("/\\"))
            n = tables_to_sql(tables, args.output, db_name=db_name)
            print(f"\nSQL-файл: {args.output}  ({n:,} записей)")
        return

    # ── SQL/CSV → Cronos ─────────────────────────────────────────────
    if not os.path.isfile(args.source):
        print(f"Файл не найден: {args.source}", file=sys.stderr); sys.exit(1)

    db_name = args.name or os.path.splitext(os.path.basename(args.source))[0]
    print(f"Файл:  {args.source}")
    print(f"Вывод: {args.output}")
    print(f"База:  {db_name}")
    print(f"Кодировка: {detect_encoding(args.source)}\n")

    last = [0]
    def prog(done, total):
        pct = int(done/max(total,1)*100)
        if pct != last[0]:
            print(f"\rПарсинг: {pct}%  ", end='', flush=True); last[0] = pct

    ext = os.path.splitext(args.source)[1].lower()
    print("Чтение файла...")
    tables = parse_csv(args.source, progress_cb=prog) if ext=='.csv' else \
             parse_sql(args.source, progress_cb=prog)
    print()

    print(f"Таблиц: {len(tables)}")
    for t in tables:
        print(f"  {t['name']:40s} {len(t['records']):>10,} записей")

    if args.limit > 0:
        for t in tables: t["records"] = t["records"][:args.limit]

    print("\nНормализация...")
    tables = normalize_tables(tables, log_cb=print,
                               do_phone=not args.no_phone,
                               do_passport=not args.no_pass,
                               do_fio=not args.no_fio,
                               do_address=not args.no_addr)

    print("\nЗапись Cronos-файлов...")
    last[0] = -1
    def wprog(done, total):
        pct = int(done/max(total,1)*100)
        if pct != last[0]:
            print(f"\rЗапись: {pct}%  ", end='', flush=True); last[0] = pct

    stats = write_cronos(tables, args.output, db_name=db_name, progress_cb=wprog)
    print()
    print(f"\nГотово! Таблиц: {stats['tables']}, записей: {stats['records']:,}")
    if "warning" in stats:
        print(f"⚠  {stats['warning']}")
    print(f"Файлы: {args.output}")


# ═══════════════════════════════════════════════════════════════════
#  Точка входа
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli_main()
    else:
        App().mainloop()
