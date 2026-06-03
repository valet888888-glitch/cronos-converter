#!/usr/bin/env python3
"""
SQL/CSV/Cronos ↔ CronosPRO Конвертер v2.1
Двусторонняя конвертация + связывание таблиц.

Запуск:
    python sql_to_cronos.py                              # GUI
    python sql_to_cronos.py dump.sql      ./out/         # SQL  → Cronos
    python sql_to_cronos.py data.csv      ./out/         # CSV  → Cronos
    python sql_to_cronos.py ./csv_folder/ ./out/         # Папка CSV → Cronos
    python sql_to_cronos.py ./cronos_db/  ./out/ --export csv
    python sql_to_cronos.py ./cronos_db/  dump.sql --export sql

Требования: Python 3.7+, только стандартная библиотека.
"""

import os, sys, re, struct, csv, io, time, threading, argparse
from tkinter import (Tk, ttk, filedialog, messagebox, scrolledtext,
                     StringVar, IntVar, BooleanVar, Frame, Label, Entry,
                     Button, LabelFrame, Checkbutton, Radiobutton, END,
                     DISABLED, NORMAL, LEFT, RIGHT, BOTH, X, W, Y, N, S,
                     Listbox, SINGLE)

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
# Обратная таблица — вычислить один раз, а не при каждом вызове _kod_encode
_KOD_INV = [0] * 256
for _i, _x in enumerate(_KOD_TABLE):
    _KOD_INV[_x] = _i

def _kod_encode(shift: int, data: bytes) -> bytes:
    return bytes(_KOD_INV[(b + i + shift) % 256] for i, b in enumerate(data))


# ═══════════════════════════════════════════════════════════════════
#  Транслитерация для cp1251 — на уровне модуля, не внутри функции
# ═══════════════════════════════════════════════════════════════════

_TRANSLIT = {
    'Қ':'К','қ':'к','Ғ':'Г','ғ':'г','Ұ':'У','ұ':'у','Ү':'У','ү':'у',
    'Ө':'О','ө':'о','Ң':'Н','ң':'н','Ә':'А','ә':'а','І':'И','і':'и',
    'Һ':'Х','һ':'х','Є':'Е','є':'е','Ї':'И','ї':'и',
    'Ё':'Е','ё':'е',
    '—':'-','–':'-','…':'...','«':'<<','»':'>>',
    '"':'"', '"':'"', '‘':"'", '’':"'", ' ':' ', '­':'',
}


# ═══════════════════════════════════════════════════════════════════
#  Определение кодировки
# ═══════════════════════════════════════════════════════════════════

_SQL_CHARSET_MAP = {
    'utf8mb4':'utf-8','utf8':'utf-8','utf-8':'utf-8',
    'cp1251':'cp1251','win1251':'cp1251','windows1251':'cp1251',
    'windows-1251':'cp1251','1251':'cp1251',
    'koi8r':'koi8-r','koi8-r':'koi8-r',
    'latin1':'latin-1','latin-1':'latin-1','iso88591':'latin-1',
}

def detect_encoding(path: str) -> str:
    with open(path, 'rb') as f:
        raw = f.read(65536)
    if raw.startswith(b'\xef\xbb\xbf'): return 'utf-8-sig'
    if raw.startswith(b'\xff\xfe'):      return 'utf-16-le'
    for pat in (rb'SET\s+NAMES\s+([a-zA-Z0-9_-]+)',
                rb'character[_\s]set[_\s]client\s*=\s*([a-zA-Z0-9_-]+)'):
        m = re.search(pat, raw[:4096], re.I)
        if m:
            dec = m.group(1).decode('ascii','ignore').lower().replace('-','').replace('_','')
            for key, enc in _SQL_CHARSET_MAP.items():
                if dec.startswith(key.replace('-','').replace('_','')):
                    return enc
    try:
        raw.decode('utf-8'); return 'utf-8'
    except UnicodeDecodeError:
        pass
    cp = sum(1 for b in raw if 0xC0 <= b <= 0xFF)
    k8 = sum(1 for b in raw if 0xE0 <= b <= 0xFF)
    return 'cp1251' if cp >= k8 else 'koi8-r'


# ═══════════════════════════════════════════════════════════════════
#  SQL-парсер
# ═══════════════════════════════════════════════════════════════════

# БАГ-ФИКС: str.maketrans возвращает dict с int-ключами (ord-значения),
# поэтому .get('n', 'n') всегда возвращало 'n'. Используем обычный dict.
_SQL_UNESCAPE = {'n':'\n','r':'\r','t':'\t','0':'\0','Z':'\x1a','b':'\b'}

def _split_values(raw: str) -> list:
    """Разбирает VALUES-строку с учётом кавычек и SQL-escapes."""
    vals=[]; cur=[]; in_q=False; q_ch=''; i=0
    while i < len(raw):
        ch = raw[i]
        if in_q and ch == '\\' and i+1 < len(raw):
            nxt = raw[i+1]
            if nxt in (q_ch, '\\'):
                cur.append(nxt)
            elif nxt in _SQL_UNESCAPE:
                cur.append(_SQL_UNESCAPE[nxt])
            else:
                cur.append(nxt)
            i += 2; continue
        if not in_q and ch in ('"',"'"):
            in_q=True; q_ch=ch; i+=1; continue
        if in_q and ch == q_ch:
            in_q=False; i+=1; continue
        if not in_q and ch == ',':
            vals.append(''.join(cur).strip()); cur=[]; i+=1; continue
        cur.append(ch); i+=1
    vals.append(''.join(cur).strip())
    return ['' if v.upper().strip() == 'NULL' else v for v in vals]


def parse_sql(path: str, progress_cb=None) -> list:
    encoding  = detect_encoding(path)
    file_size = os.path.getsize(path)

    re_create = re.compile(r'CREATE\s+TABLE\s+[`"]?(\w+)[`"]?', re.I)
    re_col    = re.compile(r'^\s*[`"](\w+)[`"]\s+\w', re.I|re.M)
    re_insert = re.compile(
        r'INSERT\s+(?:LOW_PRIORITY\s+|IGNORE\s+)?INTO\s+[`"]?(\w+)[`"]?'
        r'\s*(?:\(([^)]+)\))?\s*VALUES\s*(.*)',
        re.I|re.S)
    # Парсим строки VALUES вручную — regexp с вложенными скобками ненадёжен
    # для сложных случаев (функции, подзапросы)

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
            tbl, col_str, vals_str = m.group(1), m.group(2), m.group(3)

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

            for vals in _iter_value_rows(vals_str):
                row = ({cols[i]: vals[i] if i < len(vals) else ''
                        for i in range(len(cols))} if cols
                       else {f"col{i}": v for i, v in enumerate(vals)})
                tables[tbl]["records"].append(row)
                if not tables[tbl]["fields"] and row:
                    tables[tbl]["fields"] = list(row.keys())

    return [t for t in tables.values() if t["records"]]


def _iter_value_rows(vals_str: str):
    """
    Итерирует строки VALUES: (v1,v2,...),(v1,v2,...).
    Корректно обрабатывает вложенные скобки и строки.
    """
    depth=0; in_q=False; q_ch=''; start=None; i=0
    while i < len(vals_str):
        ch = vals_str[i]
        if in_q:
            if ch == '\\' and i+1 < len(vals_str):
                i += 2; continue
            if ch == q_ch:
                in_q = False
        else:
            if ch in ('"',"'"):
                in_q=True; q_ch=ch
            elif ch == '(':
                if depth == 0:
                    start = i+1
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0 and start is not None:
                    yield _split_values(vals_str[start:i])
                    start = None
        i += 1


# ═══════════════════════════════════════════════════════════════════
#  CSV-парсер (одиночный файл)
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

    # Оцениваем число строк по выборке
    # fh.tell() нельзя вызывать внутри csv-итератора (Python запрещает после next())
    sample_lines = max(sample.count('\n'), 1)
    sample_bytes = max(len(sample.encode(encoding, errors='replace')), 1)
    est_total    = max(1, int(sample_lines * file_size / sample_bytes))

    records=[]; fields=[]
    with open(path, encoding=encoding, errors='replace', newline='') as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        fields = list(reader.fieldnames or [])
        for i, row in enumerate(reader):
            records.append(dict(row))
            if progress_cb and i % 10000 == 0:
                progress_cb(int(i/est_total*file_size), file_size)

    return [{"name": table_name, "fields": fields, "records": records}]


def parse_csv_folder(folder: str, progress_cb=None) -> list:
    """Загружает все .csv файлы из папки — каждый как отдельная таблица."""
    csv_files = sorted(
        f for f in os.listdir(folder) if f.lower().endswith('.csv')
    )
    if not csv_files:
        raise ValueError(f"CSV-файлы не найдены в {folder}")
    tables = []
    for idx, fname in enumerate(csv_files):
        path = os.path.join(folder, fname)
        def _prog(d, t, idx=idx, total=len(csv_files)):
            if progress_cb:
                progress_cb(int((idx + d/max(t,1)) / total * os.path.getsize(path)),
                            os.path.getsize(path))
        t = parse_csv(path)
        tables.extend(t)
        if progress_cb:
            progress_cb(idx+1, len(csv_files))
    return tables


# ═══════════════════════════════════════════════════════════════════
#  Встроенный Cronos-читатель (без внешних зависимостей)
# ═══════════════════════════════════════════════════════════════════

def _cro_read_name(data: bytes, pos: int):
    if pos >= len(data): return '', pos
    length = data[pos]; pos += 1
    return data[pos:pos+length].decode('cp1251', errors='replace'), pos+length


def _read_dat_records(dat_path: str) -> list:
    tad_path = os.path.splitext(dat_path)[0] + '.tad'
    if not os.path.exists(dat_path) or not os.path.exists(tad_path):
        raise FileNotFoundError(f"Файлы не найдены: {dat_path}")
    with open(dat_path,'rb') as f: dat = f.read()
    with open(tad_path,'rb') as f: tad = f.read()
    if not dat.startswith(b'CroFile\x00'):
        raise ValueError(f"Не CroFile: {dat_path}")
    records=[]; pos=8
    while pos+12 <= len(tad):
        offset, len_flags, _ = struct.unpack_from('<LLL', tad, pos); pos+=12
        if offset==0 and len_flags==0: continue
        flag     = (len_flags>>24)&0xFF
        data_len = len_flags&0x00FFFFFF
        if flag==0xFF: continue   # удалённая запись
        if offset+data_len <= len(dat):
            records.append(dat[offset:offset+data_len])
    return records


def _parse_table_def(rec: bytes):
    """Разбирает TableDefinition из записи CroStru (префикс 0x04)."""
    if not rec or rec[0] != 0x04: return None
    try:
        pos=1; pos+=2                   # unk1
        version=rec[pos]; pos+=1
        if version>1: pos+=1            # pad (только для v>1)
        unk2=rec[pos]; pos+=1
        pos+=1                          # unk3
        if unk2>5: pos+=4               # extra_dword
        pos+=4                          # unk4
        tableid=struct.unpack_from('<L',rec,pos)[0]; pos+=4
        name,   pos=_cro_read_name(rec,pos)
        _abbr,  pos=_cro_read_name(rec,pos)
        pos+=4                          # unk7
        nrfields=struct.unpack_from('<L',rec,pos)[0]; pos+=4
        fields=[]
        for _ in range(nrfields):
            if pos+2>len(rec): break
            flen=struct.unpack_from('<H',rec,pos)[0]; pos+=2
            fdata=rec[pos:pos+flen];    pos+=flen
            if len(fdata)<7: continue
            fname,_=_cro_read_name(fdata,6)
            fields.append(fname)
        return {"tableid":tableid,"name":name,"fields":fields}
    except Exception:
        return None


def parse_cronos(db_dir: str, progress_cb=None) -> list:
    files     = {f.lower():f for f in os.listdir(db_dir)}
    stru_name = files.get('crostru.dat')
    bank_name = files.get('crobank.dat')
    if not stru_name:
        raise FileNotFoundError("CroStru.dat не найден в "+db_dir)

    stru_records = _read_dat_records(os.path.join(db_dir, stru_name))

    schema={}
    for rec in stru_records:
        td=_parse_table_def(rec)
        # БАГ-ФИКС: фильтруем по tableid==0 (системная таблица Files),
        # а не по имени — имя могло быть переименовано
        if td and td["tableid"] != 0:
            schema[td["tableid"]]=td

    if not bank_name:
        return [{"name":v["name"],"fields":v["fields"][1:],"records":[]}
                for v in schema.values()]

    bank_records = _read_dat_records(os.path.join(db_dir, bank_name))
    total_bank   = len(bank_records)

    by_table={}
    for i,rec in enumerate(bank_records):
        if not rec: continue
        by_table.setdefault(rec[0],[]).append(rec[1:])
        if progress_cb and i%50000==0:
            progress_cb(i, total_bank)

    result=[]
    for tableid,tdef in sorted(schema.items()):
        # Первое поле — "Системный номер", в CroBank не хранится
        user_fields = tdef["fields"][1:] if len(tdef["fields"])>1 else tdef["fields"]
        records=[]
        for raw in by_table.get(tableid,[]):
            parts=raw.split(b'\x1e')
            row={}
            for i,fname in enumerate(user_fields):
                vb=parts[i] if i<len(parts) else b''
                try:    row[fname]=vb.decode('cp1251')
                except: row[fname]=vb.decode('latin-1',errors='replace')
            records.append(row)
        result.append({"name":tdef["name"],"fields":user_fields,"records":records})

    if progress_cb: progress_cb(total_bank, total_bank)
    return result


# ═══════════════════════════════════════════════════════════════════
#  Связывание таблиц (JOIN)
# ═══════════════════════════════════════════════════════════════════

def join_tables(tables: list,
                left_name: str,  left_key: str,
                right_name: str, right_key: str,
                result_name: str = '',
                join_type: str   = 'left') -> dict:
    """
    Выполняет LEFT или INNER JOIN двух таблиц по ключевым полям.

    join_type = 'left'  — все строки левой таблицы (NULL для несовпавших)
    join_type = 'inner' — только строки с совпадением

    Возвращает новую таблицу {"name","fields","records"}.
    """
    left  = next((t for t in tables if t["name"]==left_name),  None)
    right = next((t for t in tables if t["name"]==right_name), None)
    if not left:  raise ValueError(f"Таблица не найдена: {left_name}")
    if not right: raise ValueError(f"Таблица не найдена: {right_name}")

    # Хэш-индекс по правой таблице — O(n) вместо O(n²)
    right_idx: dict = {}
    for row in right["records"]:
        k = str(row.get(right_key,'') or '').strip()
        right_idx.setdefault(k, []).append(row)

    # Поля результата: все левые + правые без дубликатов ключа
    left_fields  = left["fields"]
    right_fields = [f for f in right["fields"] if f != right_key]

    # Разрешаем конфликты имён: правое поле получает префикс имени таблицы
    merged_fields = list(left_fields)
    field_map     = {}   # right_field → merged_field_name
    for f in right_fields:
        new_f = f if f not in left_fields else f"{right_name}__{f}"
        merged_fields.append(new_f)
        field_map[f] = new_f

    empty_right = {field_map[f]: '' for f in right_fields}

    merged_records = []
    for lrow in left["records"]:
        lkey = str(lrow.get(left_key,'') or '').strip()
        matches = right_idx.get(lkey, [])

        if matches:
            for rrow in matches:
                merged = dict(lrow)
                for f in right_fields:
                    merged[field_map[f]] = rrow.get(f,'')
                merged_records.append(merged)
        elif join_type == 'left':
            merged = dict(lrow)
            merged.update(empty_right)
            merged_records.append(merged)

    name = result_name or f"{left_name}+{right_name}"
    return {"name": name, "fields": merged_fields, "records": merged_records}


# ═══════════════════════════════════════════════════════════════════
#  Экспорт в CSV и SQL
# ═══════════════════════════════════════════════════════════════════

def tables_to_csv(tables: list, output_dir: str, progress_cb=None) -> list:
    os.makedirs(output_dir, exist_ok=True)
    written=[]
    for table in tables:
        safe = re.sub(r'[^\w\-_]','_',table["name"])
        path = os.path.join(output_dir, safe+'.csv')
        with open(path,'w',newline='',encoding='utf-8-sig') as fh:
            w=csv.DictWriter(fh,fieldnames=table["fields"],extrasaction='ignore')
            w.writeheader(); w.writerows(table["records"])
        written.append(path)
    return written


def tables_to_sql(tables: list, output_path: str,
                  db_name: str='export', progress_cb=None) -> int:
    total=0
    with open(output_path,'w',encoding='utf-8') as fh:
        fh.write(f"-- SQL↔Cronos Converter  db={db_name}\nSET NAMES utf8mb4;\n\n")
        for table in tables:
            tname=table["name"]; flds=table["fields"]; recs=table["records"]
            safe_t=tname.replace('`','``')
            fh.write(f"DROP TABLE IF EXISTS `{safe_t}`;\n")
            col_lines=[f"  `{f.replace('`','``')}` text" for f in flds]
            fh.write(f"CREATE TABLE `{safe_t}` (\n")
            fh.write(",\n".join(col_lines))
            fh.write("\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n\n")
            if recs:
                col_part=", ".join(f"`{f.replace('`','``')}`" for f in flds)
                fh.write(f"INSERT INTO `{safe_t}` ({col_part}) VALUES\n")
                rows_sql=[]
                for i,rec in enumerate(recs):
                    vals=[]
                    for f in flds:
                        v=str(rec.get(f,''or''))
                        v=v.replace('\\','\\\\').replace("'","\\'").replace('\n','\\n').replace('\r','\\r')
                        vals.append(f"'{v}'")
                    rows_sql.append(f"({', '.join(vals)})")
                    total+=1
                    if progress_cb and i%50000==0: progress_cb(i,len(recs))
                fh.write(',\n'.join(rows_sql)+';\n\n')
    return total


# ═══════════════════════════════════════════════════════════════════
#  Cronos-writer
# ═══════════════════════════════════════════════════════════════════

def _cro_name(s:str)->bytes:
    b=s.encode('cp1251',errors='replace'); return bytes([min(len(b),255)])+b[:255]
def _cro_inline(data:bytes)->bytes:
    return struct.pack("<L",0x80000000|len(data))+data
def _cro_ref(recno:int)->bytes:
    return struct.pack("<L",recno)

def _infer_type(samples:list)->tuple:
    ne=[str(v) for v in samples if v and str(v).strip() and str(v).upper()!='NULL']
    if not ne: return 2,256
    if all(re.fullmatch(r'-?\d+',v.strip()) for v in ne): return 1,20
    if (sum(1 for v in ne if re.fullmatch(r'\d{2,4}[-./]\d{1,2}[-./]\d{1,4}',v.strip()))
            /len(ne)>0.8): return 4,10
    ml=max(len(v) for v in ne)
    return (3,65535) if ml>500 else (2,max(ml+50,64))

def _enc_field(idx:int,name:str,typ:int,maxval:int=256)->bytes:
    d=bytearray()
    d+=struct.pack("<H",typ); d+=struct.pack("<L",idx); d+=_cro_name(name)
    d+=struct.pack("<L",0);   d+=bytes([1 if typ else 0])
    if typ:
        d+=struct.pack("<L",idx); d+=struct.pack("<L",maxval)
        d+=struct.pack("<L",0x10019); d+=b"\x00"*13
    return bytes(d)

def _enc_table(tableid:int,name:str,fdefs:list)->bytes:
    d=bytearray()
    d+=struct.pack("<H",0); d+=bytes([3,0,9,1]); d+=struct.pack("<L",2)
    d+=struct.pack("<L",0); d+=struct.pack("<L",tableid)
    d+=_cro_name(name);     d+=_cro_name(name[:2])
    d+=struct.pack("<L",1); d+=struct.pack("<L",len(fdefs))
    for fd in fdefs: d+=struct.pack("<H",len(fd))+fd
    d+=struct.pack("<L",0); d+=struct.pack("<L",0)
    d+=bytes([2]);           d+=struct.pack("<L",0); d+=struct.pack("<L",0)
    return bytes(d)

def _enc_dbdef(db_name:str, table_recnos:list)->bytes:
    d=bytearray(); d+=bytes([0x03])
    d+=_cro_name("Bank");       d+=_cro_inline(b"\x00\x02"+b"\x00"*9)
    d+=_cro_name("BankId");     d+=_cro_inline(b"00000001")
    d+=_cro_name("BankName");   d+=_cro_inline(db_name.encode('cp1251','replace'))
    files_def=_enc_table(0,"Files",[_enc_field(0,"Системный номер",0),_enc_field(1,"Name",2,256)])
    d+=_cro_name("Base000");    d+=_cro_inline(files_def)
    d+=_cro_name("Formuls000"); d+=_cro_inline(b"\x00"*8)
    d+=_cro_name("Formuls001"); d+=_cro_inline(b"\x00"*8)
    for i,recno in enumerate(table_recnos,1):
        d+=_cro_name(f"Base{i:03d}"); d+=_cro_ref(recno)
    shift=0xC2; plain=struct.pack("<LLL",0x57,0,0)+b"\x00"*8
    d+=_cro_name("NS1");    d+=_cro_inline(bytes([0x02,shift])+_kod_encode(shift,plain))
    d+=_cro_name("NS2");    d+=_cro_inline(struct.pack("<L",0x57))
    d+=_cro_name("Version"); d+=_cro_inline(b"\x2d\x36")
    return bytes(d)

def _safe_cp1251(s:str)->bytes:
    try: return s.encode('cp1251')
    except (UnicodeEncodeError,UnicodeDecodeError): pass
    result=[]
    for ch in s:
        try: result.append(ch.encode('cp1251'))
        except: result.append(_TRANSLIT.get(ch,'?').encode('cp1251',errors='replace'))
    return b''.join(result)

def _enc_bank_record(tableid:int,user_fields:list,row:dict)->tuple:
    parts=[]; lost=0
    for f in user_fields:
        rv=str(row.get(f,''or''))
        enc=_safe_cp1251(rv)
        lost+=max(enc.count(b'?')-rv.count('?'),0)
        parts.append(enc)
    return bytes([tableid])+b"\x1e".join(parts), lost

class _CroWriter:
    def __init__(self,blocksize=0x40): self.blocksize=blocksize; self._recs=[]
    def add(self,data:bytes):          self._recs.append(data)
    def build(self)->tuple:
        dat=bytearray(); tad=bytearray()
        dat+=b"CroFile\x00"+struct.pack("<H",0)+b"01.02"+struct.pack("<HH",0,self.blocksize)+b"\x00"*0xE9
        tad+=struct.pack("<LL",0,0)
        for rec in self._recs:
            tad+=struct.pack("<LLL",len(dat),(0x80<<24)|len(rec),0); dat+=rec
        return bytes(dat),bytes(tad)

def write_cronos(tables:list, output_dir:str,
                 db_name:str='export', progress_cb=None)->dict:
    os.makedirs(output_dir,exist_ok=True)
    stru=_CroWriter(0x0200); bank=_CroWriter(0x0040); index=_CroWriter(0x0400)
    table_entries=[]; total=sum(len(t.get("records",[])) for t in tables)
    done=0; lost_chars=0

    for t_idx,table in enumerate(tables):
        tableid=t_idx+1; tname=table["name"]
        all_fnames=table.get("fields",[]); records=table.get("records",[])
        user_fields=[f for f in all_fnames if f not in ("Системный номер","__recno__")]
        sample=min(100,len(records))
        fdefs=[_enc_field(0,"Системный номер",0)]
        for i,fname in enumerate(user_fields,1):
            typ,maxval=_infer_type([r.get(fname,"") for r in records[:sample]])
            fdefs.append(_enc_field(i,fname,typ,maxval))
        stru.add(b"\x04"+_enc_table(tableid,tname,fdefs))
        table_entries.append((tableid,user_fields,records))

    stru._recs.insert(0,_enc_dbdef(db_name,[i+2 for i in range(len(tables))]))

    for tableid,user_fields,records in table_entries:
        for row in records:
            rb,lc=_enc_bank_record(tableid,user_fields,row)
            bank.add(rb); lost_chars+=lc; done+=1
            if progress_cb and done%5000==0: progress_cb(done,total)

    if progress_cb: progress_cb(total,total)
    for prefix,writer in [("CroStru",stru),("CroBank",bank),("CroIndex",index)]:
        dat,tad=writer.build()
        open(os.path.join(output_dir,prefix+".dat"),"wb").write(dat)
        open(os.path.join(output_dir,prefix+".tad"),"wb").write(tad)

    res={"tables":len(tables),"records":done}
    if lost_chars>0:
        res["warning"]=f"{lost_chars:,} символов заменены на '?' (emoji, казахские/укр. буквы)."
    return res


# ═══════════════════════════════════════════════════════════════════
#  Нормализация данных
# ═══════════════════════════════════════════════════════════════════

_RE_PHONE_FIELD    = re.compile(r'phone|tel(?:efon)?|mob(?:ile)?|cell|сотов|телефон|тел\b|моб|phone_?num',re.I)
_RE_PASSPORT_FIELD = re.compile(r'passport|pasport|паспорт|пасп(?:орт)?|pass_n|docum(?:ent)?|doc_n',re.I)
_RE_PASSPORT_SERIES= re.compile(r'(?:pass(?:port)?|pasport|паспорт|пасп)[_\s]?(?:ser(?:ies?)?|seria|серия|сер)',re.I)
_RE_PASSPORT_NUMBER= re.compile(r'(?:pass(?:port)?|pasport|паспорт|пасп)[_\s]?(?:num(?:ber)?|nomer|no\b|номер|ном)',re.I)
_RE_LASTNAME  = re.compile(r'^(?:last_?name|surname|фамилия|фам(?:_|$)|lastname|family(?:_name)?|familiya|fam)$',re.I)
_RE_FIRSTNAME = re.compile(r'^(?:first_?name|given_?name|имя|firstname|fn$|givenname|name$|ima$)$',re.I)
_RE_MIDDLENAME= re.compile(r'^(?:middle_?name|patronymic|отчество|отч(?:_|$)|middlename|patronym(?:a)?|patron|otchestvo|otch$)$',re.I)
_RE_ADDR_FULL  = re.compile(r'^(?:address|adres|addr(?:ess)?|адрес|full_?addr|home_?addr|адр(?:ес)?|reg_?addr|mail_?addr|место_?жит|прожив\w*)$',re.I)
_RE_ADDR_ZIP   = re.compile(r'^(?:zip|postal_?code?|postcode|index|индекс|zip_?code?|post_?index)$',re.I)
_RE_ADDR_REGION= re.compile(r'^(?:region|регион|oblast|область|province|кра[йи]|krai|kraj|субъект)$',re.I)
_RE_ADDR_CITY  = re.compile(r'^(?:city|город|gorod|town|нп|locality|settlement|населен\w*)$',re.I)
_RE_ADDR_STREET= re.compile(r'^(?:street|улица|ul(?:ica)?|ulitsa|street_?name|ул(?:_|$))$',re.I)
_RE_ADDR_HOUSE = re.compile(r'^(?:house|дом|dom|house_?num|bld(?:g)?|building|house_?number|дом_?номер)$',re.I)
_RE_ADDR_FLAT  = re.compile(r'^(?:flat|квартира|apartment|apt|kv|room|flat_?num|кв(?:_|$))$',re.I)


def normalize_phone(val:str)->str:
    if not val or not val.strip(): return val
    d=re.sub(r'\D','',val)
    if len(d)==11 and d[0]=='8': d='7'+d[1:]
    elif len(d)==10 and d[0]=='9': d='7'+d
    return d if len(d)==11 and d[0]=='7' else val

def normalize_passport(val:str)->str:
    if not val or not val.strip(): return val
    d=re.sub(r'\D','',val)
    return d[:4]+' '+d[4:] if len(d)==10 else val

def normalize_tables(tables:list, log_cb=None,
                     do_phone=True, do_passport=True,
                     do_fio=True, do_address=True)->list:
    for table in tables:
        fields=table.get("fields",[]); records=table.get("records",[]); tname=table.get("name","?")
        if not records: continue

        phone_fields = [f for f in fields if _RE_PHONE_FIELD.search(f)] if do_phone else []
        pass_single  = ([f for f in fields if _RE_PASSPORT_FIELD.search(f)
                          and not _RE_PASSPORT_SERIES.search(f)
                          and not _RE_PASSPORT_NUMBER.search(f)] if do_passport else [])
        pass_series  = (next((f for f in fields if _RE_PASSPORT_SERIES.search(f)),None) if do_passport else None)
        pass_number  = (next((f for f in fields if _RE_PASSPORT_NUMBER.search(f)),None) if do_passport else None)
        combine_pass = pass_series and pass_number and 'Паспорт' not in fields

        f_last  = (next((f for f in fields if _RE_LASTNAME.match(f)),  None) if do_fio else None)
        f_first = (next((f for f in fields if _RE_FIRSTNAME.match(f)), None) if do_fio else None)
        f_mid   = (next((f for f in fields if _RE_MIDDLENAME.match(f)),None) if do_fio else None)
        has_fio_parts = bool(f_last or f_first or f_mid)
        has_fio_field = any(f in ('ФИО','FIO','fio','fullname','full_name') for f in fields)

        f_zip=   (next((f for f in fields if _RE_ADDR_ZIP.match(f)),   None) if do_address else None)
        f_region=(next((f for f in fields if _RE_ADDR_REGION.match(f)),None) if do_address else None)
        f_city=  (next((f for f in fields if _RE_ADDR_CITY.match(f)),  None) if do_address else None)
        f_street=(next((f for f in fields if _RE_ADDR_STREET.match(f)),None) if do_address else None)
        f_house= (next((f for f in fields if _RE_ADDR_HOUSE.match(f)), None) if do_address else None)
        f_flat=  (next((f for f in fields if _RE_ADDR_FLAT.match(f)),  None) if do_address else None)
        addr_part_fields=[f for f in (f_zip,f_region,f_city,f_street,f_house,f_flat) if f]
        has_addr_parts = len(addr_part_fields)>=2
        has_addr_field = any(_RE_ADDR_FULL.match(f) for f in fields)

        ph_cnt=ps_cnt=fi_cnt=ad_cnt=0

        for rec in records:
            for pf in phone_fields:
                v=rec.get(pf,'')
                if v:
                    n=normalize_phone(str(v))
                    if n!=str(v): rec[pf]=n; ph_cnt+=1
            for pf in pass_single:
                v=rec.get(pf,'')
                if v:
                    n=normalize_passport(str(v))
                    if n!=str(v): rec[pf]=n; ps_cnt+=1
            if combine_pass:
                s=re.sub(r'\D','',str(rec.get(pass_series,''or'')))
                n=re.sub(r'\D','',str(rec.get(pass_number,'')or''))
                if s and n and len(s+n)==10:
                    rec['Паспорт']=(s+n)[:4]+' '+(s+n)[4:]; ps_cnt+=1
            if has_fio_parts and not has_fio_field:
                parts=[str(rec.get(f,''or'')).strip() for f in (f_last,f_first,f_mid) if f]
                fv=' '.join(p for p in parts if p)
                if fv: rec['ФИО']=fv; fi_cnt+=1
            if has_addr_parts and not has_addr_field:
                def _g(f): return str(rec.get(f,''or'')).strip() if f else ''
                pts=[]
                if f_zip:    v=_g(f_zip);    v and pts.append(v)
                if f_region: v=_g(f_region); v and pts.append(v)
                if f_city:   v=_g(f_city);   v and pts.append(v)
                if f_street: v=_g(f_street); v and pts.append("ул. "+v)
                if f_house:  v=_g(f_house);  v and pts.append("д. "+v)
                if f_flat:   v=_g(f_flat);   v and pts.append("кв. "+v)
                av=', '.join(pts)
                if av: rec['Адрес']=av; ad_cnt+=1

        if combine_pass and ps_cnt>0 and 'Паспорт' not in fields:
            at=fields.index(pass_series) if pass_series in fields else len(fields)
            fields.insert(at,'Паспорт'); table["fields"]=fields
        if has_fio_parts and not has_fio_field and fi_cnt>0:
            at=0
            for i,f in enumerate(fields):
                if re.match(r'^(id|сис|sys|recno|__)',f,re.I): at=i+1
            fields.insert(at,'ФИО'); table["fields"]=fields
        if has_addr_parts and not has_addr_field and ad_cnt>0:
            at=(fields.index('ФИО')+1) if 'ФИО' in fields else 0
            for i,f in enumerate(fields):
                if re.match(r'^(id|сис|sys|recno|__)',f,re.I): at=i+1
            if 'ФИО' in fields: at=fields.index('ФИО')+1
            fields.insert(at,'Адрес'); table["fields"]=fields

        if log_cb:
            msgs=[]
            if ph_cnt>0: msgs.append(f"тел: {ph_cnt:,}")
            if ps_cnt>0: msgs.append(f"паспорт: {ps_cnt:,}")
            if fi_cnt>0: msgs.append(f"ФИО из [{'+'.join(f for f in (f_last,f_first,f_mid) if f)}]: {fi_cnt:,}")
            if ad_cnt>0: msgs.append(f"Адрес из [{'+'.join(addr_part_fields)}]: {ad_cnt:,}")
            if msgs: log_cb(f"  [{tname}] нормализация: {', '.join(msgs)}")
    return tables


# ═══════════════════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════════════════

class App(Tk):
    def __init__(self):
        super().__init__()
        self.title("SQL/CSV ↔ CronosPRO Конвертер v2.1")
        self.resizable(True,True); self.minsize(720,640)
        self._tables_cache: list = []   # для Tab 3 (связывание)
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────

    def _build_ui(self):
        nb=ttk.Notebook(self); nb.pack(fill=BOTH,expand=True,padx=6,pady=6)
        t1=Frame(nb); nb.add(t1,text="  SQL/CSV → Cronos  ")
        t2=Frame(nb); nb.add(t2,text="  Cronos → CSV/SQL  ")
        t3=Frame(nb); nb.add(t3,text="  Связать таблицы  ")
        self._build_import_tab(t1)
        self._build_export_tab(t2)
        self._build_join_tab(t3)

    # ─── Tab 1: импорт ─────────────────────────────────────────────

    def _build_import_tab(self,p):
        pad=dict(padx=8,pady=3)
        f1=LabelFrame(p,text=" Исходный файл или папка (SQL / CSV / папка с CSV) ")
        f1.pack(fill=X,**pad)
        self.src_var=StringVar()
        Entry(f1,textvariable=self.src_var,width=60).pack(side=LEFT,padx=6,pady=5,fill=X,expand=True)
        Button(f1,text="Файл…",command=self._pick_src_file).pack(side=LEFT,padx=2)
        Button(f1,text="Папка…",command=self._pick_src_folder).pack(side=LEFT,padx=2)

        f2=LabelFrame(p,text=" Папка вывода Cronos ")
        f2.pack(fill=X,**pad)
        self.dst_var=StringVar()
        Entry(f2,textvariable=self.dst_var,width=60).pack(side=LEFT,padx=6,pady=5,fill=X,expand=True)
        Button(f2,text="Обзор…",command=self._pick_dst).pack(side=LEFT,padx=4)

        fp=LabelFrame(p,text=" Параметры ")
        fp.pack(fill=X,**pad)
        Label(fp,text="Имя базы:").grid(row=0,column=0,sticky=W,padx=6,pady=3)
        self.name_var=StringVar(value="export")
        Entry(fp,textvariable=self.name_var,width=28).grid(row=0,column=1,sticky=W)
        Label(fp,text="Лимит записей (0=все):").grid(row=1,column=0,sticky=W,padx=6,pady=3)
        self.limit_var=StringVar(value="0")
        Entry(fp,textvariable=self.limit_var,width=12).grid(row=1,column=1,sticky=W)

        fn=LabelFrame(p,text=" Нормализация ")
        fn.pack(fill=X,**pad)
        self.norm_phone=BooleanVar(value=True); self.norm_pass=BooleanVar(value=True)
        self.norm_fio=BooleanVar(value=True);   self.norm_addr=BooleanVar(value=True)
        Checkbutton(fn,text="Телефоны → 79XXXXXXXXX", variable=self.norm_phone).grid(row=0,column=0,sticky=W,padx=8,pady=2)
        Checkbutton(fn,text="Паспорт → XXXX XXXXXX",  variable=self.norm_pass).grid(row=0,column=1,sticky=W,padx=8,pady=2)
        Checkbutton(fn,text="Объединить ФИО",          variable=self.norm_fio).grid(row=1,column=0,sticky=W,padx=8,pady=2)
        Checkbutton(fn,text="Объединить Адрес",        variable=self.norm_addr).grid(row=1,column=1,sticky=W,padx=8,pady=2)

        fpg=LabelFrame(p,text=" Прогресс ")
        fpg.pack(fill=X,**pad)
        self.i_prog=IntVar()
        ttk.Progressbar(fpg,variable=self.i_prog,maximum=100).pack(fill=X,padx=6,pady=4)
        self.i_status=StringVar(value="Готов")
        Label(fpg,textvariable=self.i_status,anchor=W).pack(fill=X,padx=6)

        fl=LabelFrame(p,text=" Лог ")
        fl.pack(fill=BOTH,expand=True,**pad)
        self.i_log=scrolledtext.ScrolledText(fl,height=8,state=DISABLED,font=("Consolas",9))
        self.i_log.pack(fill=BOTH,expand=True,padx=4,pady=4)

        bf=Frame(p); bf.pack(fill=X,padx=8,pady=6)
        self.i_btn=Button(bf,text="▶  Конвертировать в Cronos",command=self._start_import,
                          bg='#1d4ed8',fg='white',font=('',10,'bold'),padx=12,pady=5)
        self.i_btn.pack(side=LEFT)
        Button(bf,text="Открыть папку",command=lambda:self._open_dir(self.dst_var.get()),padx=8).pack(side=LEFT,padx=6)
        Button(bf,text="Выход",command=self.destroy,padx=8).pack(side=RIGHT)

    # ─── Tab 2: экспорт ────────────────────────────────────────────

    def _build_export_tab(self,p):
        pad=dict(padx=8,pady=3)
        f1=LabelFrame(p,text=" Папка с базой Cronos (CroBank.dat + CroStru.dat) ")
        f1.pack(fill=X,**pad)
        self.cro_src_var=StringVar()
        Entry(f1,textvariable=self.cro_src_var,width=60).pack(side=LEFT,padx=6,pady=5,fill=X,expand=True)
        Button(f1,text="Обзор…",command=self._pick_cro_src).pack(side=LEFT,padx=4)

        f2=LabelFrame(p,text=" Папка/файл вывода ")
        f2.pack(fill=X,**pad)
        self.cro_dst_var=StringVar()
        Entry(f2,textvariable=self.cro_dst_var,width=60).pack(side=LEFT,padx=6,pady=5,fill=X,expand=True)
        Button(f2,text="Обзор…",command=self._pick_cro_dst).pack(side=LEFT,padx=4)

        ff=LabelFrame(p,text=" Формат вывода ")
        ff.pack(fill=X,**pad)
        self.export_fmt=StringVar(value="csv")
        Radiobutton(ff,text="CSV (по одному файлу на таблицу)",variable=self.export_fmt,value="csv").pack(anchor=W,padx=10,pady=3)
        Radiobutton(ff,text="SQL (MySQL INSERT-дамп)",variable=self.export_fmt,value="sql").pack(anchor=W,padx=10,pady=3)

        fpg=LabelFrame(p,text=" Прогресс ")
        fpg.pack(fill=X,**pad)
        self.e_prog=IntVar()
        ttk.Progressbar(fpg,variable=self.e_prog,maximum=100).pack(fill=X,padx=6,pady=4)
        self.e_status=StringVar(value="Готов")
        Label(fpg,textvariable=self.e_status,anchor=W).pack(fill=X,padx=6)

        fl=LabelFrame(p,text=" Лог ")
        fl.pack(fill=BOTH,expand=True,**pad)
        self.e_log=scrolledtext.ScrolledText(fl,height=8,state=DISABLED,font=("Consolas",9))
        self.e_log.pack(fill=BOTH,expand=True,padx=4,pady=4)

        bf=Frame(p); bf.pack(fill=X,padx=8,pady=6)
        self.e_btn=Button(bf,text="▶  Экспортировать из Cronos",command=self._start_export,
                          bg='#15803d',fg='white',font=('',10,'bold'),padx=12,pady=5)
        self.e_btn.pack(side=LEFT)
        Button(bf,text="Открыть папку",command=lambda:self._open_dir(os.path.dirname(self.cro_dst_var.get())
               if os.path.isfile(self.cro_dst_var.get()) else self.cro_dst_var.get()),padx=8).pack(side=LEFT,padx=6)
        Button(bf,text="Выход",command=self.destroy,padx=8).pack(side=RIGHT)

    # ─── Tab 3: связывание таблиц ──────────────────────────────────

    def _build_join_tab(self,p):
        pad=dict(padx=8,pady=3)

        # Загрузка
        fl=LabelFrame(p,text=" Загрузить данные ")
        fl.pack(fill=X,**pad)
        self.j_src_var=StringVar()
        Entry(fl,textvariable=self.j_src_var,width=52).pack(side=LEFT,padx=6,pady=5,fill=X,expand=True)
        Button(fl,text="Файл…",command=self._j_pick_file).pack(side=LEFT,padx=2)
        Button(fl,text="Папка…",command=self._j_pick_folder).pack(side=LEFT,padx=2)
        Button(fl,text="Загрузить",command=self._j_load,bg='#374151',fg='white',padx=8).pack(side=LEFT,padx=4)

        # Список таблиц
        ft=LabelFrame(p,text=" Загруженные таблицы ")
        ft.pack(fill=X,**pad)
        self.j_table_list=Listbox(ft,height=5,font=("Consolas",9),selectmode=SINGLE)
        sb=ttk.Scrollbar(ft,orient='vertical',command=self.j_table_list.yview)
        self.j_table_list.configure(yscrollcommand=sb.set)
        self.j_table_list.pack(side=LEFT,fill=BOTH,expand=True,padx=4,pady=4)
        sb.pack(side=LEFT,fill=Y)

        # JOIN-конфигуратор
        fj=LabelFrame(p,text=" Связать таблицы ")
        fj.pack(fill=X,**pad)

        Label(fj,text="Левая таблица:").grid(row=0,column=0,sticky=W,padx=6,pady=3)
        self.j_left_tbl=StringVar()
        self.j_left_cb=ttk.Combobox(fj,textvariable=self.j_left_tbl,width=22,state='readonly')
        self.j_left_cb.grid(row=0,column=1,padx=4)
        self.j_left_cb.bind('<<ComboboxSelected>>',self._j_update_keys)

        Label(fj,text="Ключ:").grid(row=0,column=2,sticky=W,padx=4)
        self.j_left_key=StringVar()
        self.j_left_key_cb=ttk.Combobox(fj,textvariable=self.j_left_key,width=18,state='readonly')
        self.j_left_key_cb.grid(row=0,column=3,padx=4)

        Label(fj,text="Правая таблица:").grid(row=1,column=0,sticky=W,padx=6,pady=3)
        self.j_right_tbl=StringVar()
        self.j_right_cb=ttk.Combobox(fj,textvariable=self.j_right_tbl,width=22,state='readonly')
        self.j_right_cb.grid(row=1,column=1,padx=4)
        self.j_right_cb.bind('<<ComboboxSelected>>',self._j_update_keys)

        Label(fj,text="Ключ:").grid(row=1,column=2,sticky=W,padx=4)
        self.j_right_key=StringVar()
        self.j_right_key_cb=ttk.Combobox(fj,textvariable=self.j_right_key,width=18,state='readonly')
        self.j_right_key_cb.grid(row=1,column=3,padx=4)

        Label(fj,text="Тип связи:").grid(row=2,column=0,sticky=W,padx=6,pady=3)
        self.j_type=StringVar(value="left")
        Radiobutton(fj,text="LEFT (все строки левой)",variable=self.j_type,value="left").grid(row=2,column=1,sticky=W)
        Radiobutton(fj,text="INNER (только совпадения)",variable=self.j_type,value="inner").grid(row=2,column=2,columnspan=2,sticky=W)

        Label(fj,text="Имя результата:").grid(row=3,column=0,sticky=W,padx=6,pady=3)
        self.j_result_name=StringVar()
        Entry(fj,textvariable=self.j_result_name,width=28).grid(row=3,column=1,sticky=W)
        Button(fj,text="▶ Объединить",command=self._j_join,
               bg='#7c3aed',fg='white',padx=10).grid(row=3,column=2,columnspan=2,padx=8)

        # Сохранить результат
        fs=LabelFrame(p,text=" Сохранить результат ")
        fs.pack(fill=X,**pad)
        Label(fs,text="Таблица:").grid(row=0,column=0,sticky=W,padx=6,pady=3)
        self.j_save_tbl=StringVar()
        self.j_save_cb=ttk.Combobox(fs,textvariable=self.j_save_tbl,width=28,state='readonly')
        self.j_save_cb.grid(row=0,column=1,padx=4)
        Label(fs,text="Формат:").grid(row=0,column=2,sticky=W,padx=6)
        self.j_fmt=StringVar(value="cronos")
        Radiobutton(fs,text="Cronos",variable=self.j_fmt,value="cronos").grid(row=0,column=3,sticky=W)
        Radiobutton(fs,text="CSV",   variable=self.j_fmt,value="csv").grid(row=0,column=4,sticky=W)
        Radiobutton(fs,text="SQL",   variable=self.j_fmt,value="sql").grid(row=0,column=5,sticky=W)
        Label(fs,text="Вывод:").grid(row=1,column=0,sticky=W,padx=6,pady=3)
        self.j_dst_var=StringVar()
        Entry(fs,textvariable=self.j_dst_var,width=38).grid(row=1,column=1,columnspan=4,sticky=W,padx=4)
        Button(fs,text="Обзор…",command=self._j_pick_dst).grid(row=1,column=5,padx=4)
        Button(fs,text="Сохранить",command=self._j_save,bg='#15803d',fg='white',padx=10).grid(row=2,column=0,columnspan=6,pady=6)

        # Лог
        fl2=LabelFrame(p,text=" Лог ")
        fl2.pack(fill=BOTH,expand=True,**pad)
        self.j_log=scrolledtext.ScrolledText(fl2,height=7,state=DISABLED,font=("Consolas",9))
        self.j_log.pack(fill=BOTH,expand=True,padx=4,pady=4)

    # ── helpers ────────────────────────────────────────────────────

    def _open_dir(self,d):
        if d and os.path.isdir(d):
            os.startfile(d) if sys.platform=='win32' else os.system(f'open "{d}"')

    def _pick_src_file(self):
        p=filedialog.askopenfilename(title="Исходный файл",
            filetypes=[("SQL/CSV","*.sql *.csv"),("All","*.*")])
        if p:
            self.src_var.set(p); base=os.path.splitext(os.path.basename(p))[0]
            if self.name_var.get() in ("export",""): self.name_var.set(base)
            if not self.dst_var.get(): self.dst_var.set(os.path.join(os.path.dirname(p),base+"_cronos"))

    def _pick_src_folder(self):
        p=filedialog.askdirectory(title="Папка с CSV-файлами")
        if p:
            self.src_var.set(p); base=os.path.basename(p)
            if self.name_var.get() in ("export",""): self.name_var.set(base)
            if not self.dst_var.get(): self.dst_var.set(p+"_cronos")

    def _pick_dst(self):
        p=filedialog.askdirectory(title="Папка вывода Cronos")
        if p: self.dst_var.set(p)

    def _pick_cro_src(self):
        p=filedialog.askdirectory(title="Папка с базой Cronos")
        if p:
            self.cro_src_var.set(p)
            if not self.cro_dst_var.get(): self.cro_dst_var.set(p+"_export")

    def _pick_cro_dst(self):
        if self.export_fmt.get()=="sql":
            p=filedialog.asksaveasfilename(title="Сохранить SQL",defaultextension=".sql",
              filetypes=[("SQL","*.sql"),("All","*.*")])
        else:
            p=filedialog.askdirectory(title="Папка для CSV")
        if p: self.cro_dst_var.set(p)

    def _ilog(self,msg):
        self.i_log.configure(state=NORMAL); self.i_log.insert(END,msg+"\n")
        self.i_log.see(END); self.i_log.configure(state=DISABLED)
    def _elog(self,msg):
        self.e_log.configure(state=NORMAL); self.e_log.insert(END,msg+"\n")
        self.e_log.see(END); self.e_log.configure(state=DISABLED)
    def _jlog(self,msg):
        self.j_log.configure(state=NORMAL); self.j_log.insert(END,msg+"\n")
        self.j_log.see(END); self.j_log.configure(state=DISABLED)

    def _i_set(self,msg,pct=None):
        self.i_status.set(msg)
        if pct is not None: self.i_prog.set(pct)
        self.update_idletasks()
    def _e_set(self,msg,pct=None):
        self.e_status.set(msg)
        if pct is not None: self.e_prog.set(pct)
        self.update_idletasks()

    # ── Tab 1 actions ──────────────────────────────────────────────

    def _start_import(self):
        src=self.src_var.get().strip(); dst=self.dst_var.get().strip()
        name=self.name_var.get().strip() or "export"
        try: limit=int(self.limit_var.get() or 0)
        except: limit=0
        if not src or not (os.path.isfile(src) or os.path.isdir(src)):
            messagebox.showerror("Ошибка","Укажите корректный файл или папку"); return
        if not dst: messagebox.showerror("Ошибка","Укажите папку вывода"); return
        self.i_btn.config(state=DISABLED)
        self.i_log.configure(state=NORMAL); self.i_log.delete("1.0",END); self.i_log.configure(state=DISABLED)
        threading.Thread(target=self._run_import,args=(src,dst,name,limit),daemon=True).start()

    def _run_import(self,src,dst,name,limit):
        t0=time.time()
        try:
            if os.path.isdir(src):
                self._ilog(f"Папка: {src}"); self._i_set("Чтение CSV...",0)
                def prog(d,t): self._i_set(f"Файл {d}/{t}",int(d/max(t,1)*50))
                tables=parse_csv_folder(src,progress_cb=prog)
            else:
                ext=os.path.splitext(src)[1].lower()
                mb=os.path.getsize(src)/1024/1024
                self._ilog(f"Файл: {os.path.basename(src)} ({mb:.1f} MB)")
                self._ilog(f"Кодировка: {detect_encoding(src)}")
                self._i_set("Чтение...",0)
                def prog(d,t): self._i_set(f"Парсинг: {d/1024/1024:.1f}/{t/1024/1024:.1f} MB",int(d/max(t,1)*50))
                tables=parse_csv(src,progress_cb=prog) if ext=='.csv' else parse_sql(src,progress_cb=prog)

            self._ilog(f"\nНайдено таблиц: {len(tables)}")
            for t in tables: self._ilog(f"  {t['name']:40s} {len(t['records']):>10,} записей  ({len(t['fields'])} полей)")

            if limit>0:
                for t in tables: t["records"]=t["records"][:limit]
                self._ilog(f"\nЛимит: {limit} записей/таблицу")

            self._ilog("\nНормализация...")
            tables=normalize_tables(tables,log_cb=self._ilog,
                do_phone=self.norm_phone.get(),do_passport=self.norm_pass.get(),
                do_fio=self.norm_fio.get(),do_address=self.norm_addr.get())

            total=sum(len(t["records"]) for t in tables)
            self._ilog(f"\nИтого: {total:,} записей")
            self._i_set("Запись Cronos...",50)
            def wprog(d,t): self._i_set(f"Запись: {d:,}/{t:,}",50+int(d/max(t,1)*50))
            stats=write_cronos(tables,dst,db_name=name,progress_cb=wprog)

            el=time.time()-t0
            self._ilog(f"\n✓ Готово за {el:.1f} сек")
            self._ilog(f"Таблиц: {stats['tables']}, записей: {stats['records']:,}")
            if "warning" in stats: self._ilog(f"⚠  {stats['warning']}")
            self._ilog(f"Вывод: {dst}")
            for fn in ("CroStru.dat","CroStru.tad","CroBank.dat","CroBank.tad","CroIndex.dat","CroIndex.tad"):
                pp=os.path.join(dst,fn); sz=os.path.getsize(pp) if os.path.exists(pp) else 0
                self._ilog(f"  {fn}  ({sz:,} bytes)")
            self._i_set(f"✓ Готово ({el:.1f} сек)",100)
            messagebox.showinfo("Готово",f"Таблиц: {stats['tables']}\nЗаписей: {stats['records']:,}\nПапка: {dst}")
        except Exception as e:
            import traceback
            self._ilog(f"\n✗ ОШИБКА: {e}\n{traceback.format_exc()}")
            self._i_set(f"Ошибка: {e}",0); messagebox.showerror("Ошибка",str(e))
        finally:
            self.i_btn.config(state=NORMAL)

    # ── Tab 2 actions ──────────────────────────────────────────────

    def _start_export(self):
        src=self.cro_src_var.get().strip(); dst=self.cro_dst_var.get().strip()
        if not src or not os.path.isdir(src): messagebox.showerror("Ошибка","Укажите папку с базой Cronos"); return
        if not dst: messagebox.showerror("Ошибка","Укажите папку/файл вывода"); return
        self.e_btn.config(state=DISABLED)
        self.e_log.configure(state=NORMAL); self.e_log.delete("1.0",END); self.e_log.configure(state=DISABLED)
        threading.Thread(target=self._run_export,args=(src,dst,self.export_fmt.get()),daemon=True).start()

    def _run_export(self,src,dst,fmt):
        t0=time.time()
        try:
            self._elog(f"База: {src}"); self._e_set("Чтение Cronos...",5)
            def rprog(d,t): self._e_set(f"Чтение: {d:,}/{t:,}",int(d/max(t,1)*60))
            tables=parse_cronos(src,progress_cb=rprog)
            self._elog(f"\nТаблиц: {len(tables)}")
            total=0
            for t in tables:
                self._elog(f"  {t['name']:40s} {len(t['records']):>10,} записей  ({len(t['fields'])} полей)")
                total+=len(t["records"])
            self._elog(f"\nВсего: {total:,} записей"); self._e_set("Запись...",65)
            def wprog(d,t): self._e_set(f"Запись: {d:,}/{t:,}",65+int(d/max(t,1)*35))
            if fmt=="csv":
                written=tables_to_csv(tables,dst,progress_cb=wprog)
                self._elog(f"\n✓ {len(written)} CSV-файлов в {dst}")
                for pp in written: self._elog(f"  {os.path.basename(pp)}  ({os.path.getsize(pp):,} bytes)")
            else:
                db_name=os.path.basename(src.rstrip("/\\"))
                n=tables_to_sql(tables,dst,db_name=db_name,progress_cb=wprog)
                self._elog(f"\n✓ SQL: {dst}  ({n:,} записей, {os.path.getsize(dst):,} bytes)")
            el=time.time()-t0; self._e_set(f"✓ Готово ({el:.1f} сек)",100)
            messagebox.showinfo("Готово",f"Таблиц: {len(tables)}\nЗаписей: {total:,}\nВремя: {el:.1f} сек")
        except Exception as e:
            import traceback
            self._elog(f"\n✗ ОШИБКА: {e}\n{traceback.format_exc()}")
            self._e_set(f"Ошибка: {e}",0); messagebox.showerror("Ошибка",str(e))
        finally:
            self.e_btn.config(state=NORMAL)

    # ── Tab 3 actions ──────────────────────────────────────────────

    def _j_pick_file(self):
        p=filedialog.askopenfilename(title="Файл данных",
            filetypes=[("SQL/CSV","*.sql *.csv"),("All","*.*")])
        if p: self.j_src_var.set(p)

    def _j_pick_folder(self):
        p=filedialog.askdirectory(title="Папка (CSV или Cronos)")
        if p: self.j_src_var.set(p)

    def _j_pick_dst(self):
        fmt=self.j_fmt.get()
        if fmt=="sql":
            p=filedialog.asksaveasfilename(defaultextension=".sql",filetypes=[("SQL","*.sql"),("All","*.*")])
        else:
            p=filedialog.askdirectory()
        if p: self.j_dst_var.set(p)

    def _j_load(self):
        src=self.j_src_var.get().strip()
        if not src: messagebox.showerror("Ошибка","Укажите источник"); return
        self._jlog(f"Загрузка: {src}")
        try:
            if os.path.isdir(src):
                # Cronos или папка CSV?
                files={f.lower() for f in os.listdir(src)}
                if 'crostru.dat' in files:
                    tables=parse_cronos(src)
                else:
                    tables=parse_csv_folder(src)
            else:
                ext=os.path.splitext(src)[1].lower()
                tables=parse_csv(src) if ext=='.csv' else parse_sql(src)

            self._tables_cache.extend(tables)
            self._j_refresh_tables()
            for t in tables:
                self._jlog(f"  + {t['name']:40s} {len(t['records']):>10,} записей  ({len(t['fields'])} полей)")
            self._jlog(f"Всего в кэше: {len(self._tables_cache)} таблиц")
        except Exception as e:
            self._jlog(f"✗ Ошибка: {e}"); messagebox.showerror("Ошибка",str(e))

    def _j_refresh_tables(self):
        names=[t["name"] for t in self._tables_cache]
        # Listbox
        self.j_table_list.delete(0,END)
        for t in self._tables_cache:
            self.j_table_list.insert(END,f"{t['name']:40s}  {len(t['records']):>10,} зап  {len(t['fields'])} полей")
        # Comboboxes
        for cb in (self.j_left_cb,self.j_right_cb,self.j_save_cb):
            cb['values']=names
        self._j_update_keys()

    def _j_update_keys(self,event=None):
        def _fields(tname):
            t=next((x for x in self._tables_cache if x["name"]==tname),None)
            return t["fields"] if t else []
        self.j_left_key_cb['values']=_fields(self.j_left_tbl.get())
        self.j_right_key_cb['values']=_fields(self.j_right_tbl.get())

    def _j_join(self):
        lt=self.j_left_tbl.get(); lk=self.j_left_key.get()
        rt=self.j_right_tbl.get(); rk=self.j_right_key.get()
        rn=self.j_result_name.get().strip() or f"{lt}+{rt}"
        if not lt or not lk or not rt or not rk:
            messagebox.showerror("Ошибка","Выберите таблицы и ключевые поля"); return
        try:
            merged=join_tables(self._tables_cache,lt,lk,rt,rk,rn,self.j_type.get())
            self._tables_cache.append(merged)
            self._j_refresh_tables()
            self.j_save_cb.set(merged["name"])
            self._jlog(f"✓ Объединено: {merged['name']}  →  {len(merged['records']):,} записей  ({len(merged['fields'])} полей)")
        except Exception as e:
            self._jlog(f"✗ Ошибка объединения: {e}"); messagebox.showerror("Ошибка",str(e))

    def _j_save(self):
        tname=self.j_save_tbl.get(); dst=self.j_dst_var.get().strip(); fmt=self.j_fmt.get()
        if not tname: messagebox.showerror("Ошибка","Выберите таблицу"); return
        if not dst:   messagebox.showerror("Ошибка","Укажите путь вывода"); return
        table=next((t for t in self._tables_cache if t["name"]==tname),None)
        if not table: messagebox.showerror("Ошибка","Таблица не найдена"); return
        try:
            if fmt=="cronos":
                stats=write_cronos([table],dst,db_name=tname)
                self._jlog(f"✓ Cronos: {dst}  ({stats['records']:,} записей)")
            elif fmt=="csv":
                written=tables_to_csv([table],dst)
                self._jlog(f"✓ CSV: {written[0]}  ({os.path.getsize(written[0]):,} bytes)")
            else:
                n=tables_to_sql([table],dst,db_name=tname)
                self._jlog(f"✓ SQL: {dst}  ({n:,} записей)")
            messagebox.showinfo("Готово",f"Сохранено: {dst}")
        except Exception as e:
            self._jlog(f"✗ Ошибка: {e}"); messagebox.showerror("Ошибка",str(e))


# ═══════════════════════════════════════════════════════════════════
#  CLI режим
# ═══════════════════════════════════════════════════════════════════

def cli_main():
    ap=argparse.ArgumentParser(
        description="SQL/CSV → Cronos  или  Cronos → CSV/SQL",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source",help="SQL-файл, CSV-файл, папка CSV или папка Cronos")
    ap.add_argument("output",help="Папка вывода или SQL-файл")
    ap.add_argument("--name",  default="",help="Имя базы данных")
    ap.add_argument("--limit", type=int,default=0,help="Лимит записей на таблицу")
    ap.add_argument("--export",choices=["csv","sql"],default=None,
                    help="Cronos → CSV или SQL (без флага — импорт в Cronos)")
    ap.add_argument("--no-phone",action="store_true"); ap.add_argument("--no-pass",action="store_true")
    ap.add_argument("--no-fio",  action="store_true"); ap.add_argument("--no-addr",action="store_true")
    args=ap.parse_args()

    if args.export:
        if not os.path.isdir(args.source): print(f"Не папка: {args.source}",file=sys.stderr); sys.exit(1)
        print(f"Cronos → {args.export.upper()}:  {args.source}")
        lp=[0]
        def rp(d,t):
            pct=int(d/max(t,1)*100)
            if pct!=lp[0]: print(f"\rЧтение: {pct}%  ",end='',flush=True); lp[0]=pct
        tables=parse_cronos(args.source,progress_cb=rp); print()
        for t in tables: print(f"  {t['name']:40s} {len(t['records']):>10,} зап")
        if args.limit>0:
            for t in tables: t["records"]=t["records"][:args.limit]
        if args.export=="csv":
            written=tables_to_csv(tables,args.output)
            for pp in written: print(f"  → {os.path.basename(pp)}  ({os.path.getsize(pp):,} bytes)")
        else:
            db_name=args.name or os.path.basename(args.source.rstrip("/\\"))
            n=tables_to_sql(tables,args.output,db_name=db_name)
            print(f"SQL: {args.output}  ({n:,} записей)")
        return

    if not os.path.exists(args.source): print(f"Не найдено: {args.source}",file=sys.stderr); sys.exit(1)
    db_name=args.name or os.path.splitext(os.path.basename(args.source.rstrip("/\\")))[0]
    print(f"Вход: {args.source}\nВывод: {args.output}\nБаза: {db_name}\n")

    lp=[0]
    def pp(d,t):
        pct=int(d/max(t,1)*100)
        if pct!=lp[0]: print(f"\rПарсинг: {pct}%  ",end='',flush=True); lp[0]=pct

    if os.path.isdir(args.source):
        tables=parse_csv_folder(args.source,progress_cb=pp)
    else:
        ext=os.path.splitext(args.source)[1].lower()
        tables=parse_csv(args.source,progress_cb=pp) if ext=='.csv' else parse_sql(args.source,progress_cb=pp)
    print()
    for t in tables: print(f"  {t['name']:40s} {len(t['records']):>10,} зап  ({len(t['fields'])} полей)")

    if args.limit>0:
        for t in tables: t["records"]=t["records"][:args.limit]

    print("\nНормализация...")
    tables=normalize_tables(tables,log_cb=print,
        do_phone=not args.no_phone,do_passport=not args.no_pass,
        do_fio=not args.no_fio,do_address=not args.no_addr)

    print("\nЗапись Cronos...")
    lp[0]=-1
    def wp(d,t):
        pct=int(d/max(t,1)*100)
        if pct!=lp[0]: print(f"\rЗапись: {pct}%  ",end='',flush=True); lp[0]=pct

    stats=write_cronos(tables,args.output,db_name=db_name,progress_cb=wp); print()
    print(f"\nГотово! Таблиц: {stats['tables']}, записей: {stats['records']:,}")
    if "warning" in stats: print(f"⚠  {stats['warning']}")


# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if len(sys.argv)>1: cli_main()
    else: App().mainloop()
