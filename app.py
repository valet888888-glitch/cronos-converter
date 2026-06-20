"""
CronosMac — веб-интерфейс для поиска по базам CronosPRO, CSV и SQL-дампам.
"""
import os, json, sys, uuid, traceback, tempfile
from flask import Flask, request, jsonify, render_template, redirect, url_for
from core.db import init_db
from core.search import search, search_cross, list_sources
from core.importer_csv import import_csv, import_sql, import_txt, _looks_like_sql
from core.importer_cronos import import_cronos
from core.cronos_parser import parse_database
from core.cronos_writer import write_cronos
from core.db import get_conn

# При запуске из PyInstaller .exe все ресурсы распакованы в sys._MEIPASS
if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS
else:
    _base = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(_base, 'web', 'templates'),
    static_folder=os.path.join(_base, 'web', 'static'),
)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB upload

init_db()


# ── Pages ──────────────────────────────────────────────────────────────────

@app.get('/')
def index():
    return render_template('index.html')


# ── API ────────────────────────────────────────────────────────────────────

@app.get('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    mode = request.args.get('mode', 'simple')
    if not q:
        return jsonify({"error": "empty query"}), 400
    if mode == 'cross':
        return jsonify(search_cross(q))
    return jsonify({"results": search(q)})


@app.get('/api/sources')
def api_sources():
    return jsonify(list_sources())


def _make_tmp(ext: str) -> str:
    """Create a temp file path that works on all platforms including Windows."""
    import tempfile as _tf
    fd, path = _tf.mkstemp(suffix=ext, prefix='cm_')
    os.close(fd)
    return path


@app.post('/api/open_folder')
def api_open_folder():
    """Open a folder in Explorer/Finder (called from JS instead of pywebview API)."""
    data = request.json or {}
    path = data.get('path', '').strip()
    if not path or not os.path.isdir(path):
        return jsonify({"ok": False})
    try:
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            import subprocess; subprocess.Popen(['open', path])
        else:
            import subprocess; subprocess.Popen(['xdg-open', path])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.post('/api/import/csv')
def api_import_csv():
    if 'file' not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files['file']
    orig_name = f.filename or 'file.csv'
    ext = os.path.splitext(orig_name)[1].lower() or '.csv'
    path = _make_tmp(ext)
    f.save(path)
    try:
        stats = import_csv(path, source_name=orig_name)
        return jsonify({"ok": True, "stats": stats})
    except Exception as e:
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@app.post('/api/import/sql')
def api_import_sql():
    if 'file' not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files['file']
    orig_name = f.filename or 'file.sql'
    ext = os.path.splitext(orig_name)[1].lower() or '.sql'
    path = _make_tmp(ext)
    f.save(path)
    try:
        stats = import_sql(path, source_name=orig_name)
        return jsonify({"ok": True, "stats": stats})
    except Exception as e:
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@app.post('/api/import/path')
def api_import_path():
    """Import large files directly by filesystem path (bypasses upload limit)."""
    data = request.json or {}
    path = data.get('path', '').strip()
    name = data.get('name', '') or os.path.basename(path)
    fmt  = data.get('format', '')  # 'sql', 'csv', 'cronos' — auto-detect if empty

    if not path or not os.path.exists(path):
        return jsonify({"error": "file not found"}), 400

    if not fmt:
        ext = os.path.splitext(path)[1].lower()
        if ext == '.txt':
            fmt = 'txt'
        elif ext == '.sql' and _looks_like_sql(path):
            fmt = 'sql'
        elif ext == '.sql':
            # .sql extension but content is not SQL (e.g. Bitrix/Cronos CSV export)
            fmt = 'csv'
        else:
            fmt = 'csv'

    if fmt == 'sql':
        stats = import_sql(path, source_name=name)
    elif fmt in ('csv', 'txt'):
        stats = import_csv(path, source_name=name) if fmt == 'csv' else import_txt(path, source_name=name)
    elif fmt == 'cronos':
        if not os.path.isdir(path):
            return jsonify({"error": "cronos requires a directory path"}), 400
        stats = import_cronos(path, name)
    else:
        return jsonify({"error": f"unknown format: {fmt}"}), 400

    return jsonify({"ok": True, "stats": stats})


@app.post('/api/import/cronos')
def api_import_cronos():
    data = request.json or {}
    db_dir = data.get('path', '')
    name   = data.get('name', os.path.basename(db_dir))
    if not db_dir or not os.path.isdir(db_dir):
        return jsonify({"error": "invalid path"}), 400
    crack = bool(data.get('crack', False))
    stats = import_cronos(db_dir, name, crack=crack)
    return jsonify({"ok": True, "stats": stats})


@app.post('/api/export/cronos')
def api_export_cronos():
    """Export a source from internal DB to CronosPRO format (.dat/.tad files)."""
    data = request.json or {}
    source_name = data.get('source_name', '')
    output_dir  = data.get('output_dir', '')
    limit       = int(data.get('limit', 0))

    if not source_name or not output_dir:
        return jsonify({"error": "source_name and output_dir required"}), 400

    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM sources WHERE name=?", (source_name,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": f"Source '{source_name}' not found"}), 404

    source_id = row["id"]
    table_rows = conn.execute(
        "SELECT DISTINCT table_name FROM records WHERE source_id=?", (source_id,)
    ).fetchall()

    tables = []
    for tr in table_rows:
        tname = tr["table_name"]
        q = "SELECT data FROM records WHERE source_id=? AND table_name=?"
        params = [source_id, tname]
        if limit > 0:
            q += " LIMIT ?"
            params.append(limit)
        recs = conn.execute(q, params).fetchall()

        records = []
        fields_set = []
        for rec in recs:
            r = json.loads(rec["data"])
            records.append(r)
            for k in r:
                if k not in fields_set:
                    fields_set.append(k)
        tables.append({"name": tname, "fields": fields_set, "records": records})

    conn.close()

    try:
        stats = write_cronos(tables, output_dir, db_name=source_name)
        return jsonify({"ok": True, "stats": stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post('/api/export/cronos/multi')
def api_export_cronos_multi():
    """
    Export several imported sources into ONE Cronos bank.
    Each source table becomes a separate table in the bank.

    Body: { "source_names": ["src1","src2",...], "output_dir": "/path", "db_name": "MyDB", "limit": 0 }
    """
    data = request.json or {}
    source_names = data.get('source_names', [])
    output_dir   = data.get('output_dir', '').strip()
    db_name      = data.get('db_name', 'export').strip() or 'export'
    limit        = int(data.get('limit', 0))

    if not source_names:
        return jsonify({"error": "source_names list is empty"}), 400
    if not output_dir:
        return jsonify({"error": "output_dir required"}), 400

    conn = get_conn()
    tables = []
    missing = []
    for sname in source_names:
        row = conn.execute("SELECT id FROM sources WHERE name=?", (sname,)).fetchone()
        if not row:
            missing.append(sname)
            continue
        source_id = row["id"]
        table_rows = conn.execute(
            "SELECT DISTINCT table_name FROM records WHERE source_id=?", (source_id,)
        ).fetchall()
        for tr in table_rows:
            tname = tr["table_name"]
            # Field list from first 100 rows
            sample_rows = conn.execute(
                "SELECT data FROM records WHERE source_id=? AND table_name=? LIMIT 100",
                (source_id, tname)
            ).fetchall()
            fields_set = []
            for rec in sample_rows:
                for k in json.loads(rec["data"]):
                    if k not in fields_set:
                        fields_set.append(k)
            # Generator streams all records without loading into RAM
            def _make_gen(sid, tn, lim):
                q = "SELECT data FROM records WHERE source_id=? AND table_name=?"
                p = [sid, tn]
                if lim > 0:
                    q += " LIMIT ?"
                    p.append(lim)
                cur = conn.execute(q, p)
                while True:
                    batch = cur.fetchmany(500)
                    if not batch:
                        break
                    for r in batch:
                        yield json.loads(r["data"])
            tables.append({"name": tname, "fields": fields_set,
                           "records": _make_gen(source_id, tname, limit)})

    if missing:
        conn.close()
        return jsonify({"error": f"Sources not found: {missing}"}), 404
    if not tables:
        conn.close()
        return jsonify({"error": "No data to export"}), 400

    try:
        stats = write_cronos(tables, output_dir, db_name=db_name)
        return jsonify({"ok": True, "stats": stats})
    except Exception as e:
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.post('/api/convert/batch')
def api_convert_batch():
    """
    Import multiple files from filesystem paths and export them into ONE Cronos bank.
    Skips the internal DB — ephemeral, in-memory style.

    Body: { "paths": ["/p1.csv", "/p2.sql",...], "output_dir": "/out", "db_name": "MyDB" }
    """
    data = request.json or {}
    paths      = data.get('paths', [])
    output_dir = data.get('output_dir', '').strip()
    db_name    = data.get('db_name', 'export').strip() or 'export'

    if not paths:
        return jsonify({"error": "paths list is empty"}), 400
    if not output_dir:
        return jsonify({"error": "output_dir required"}), 400

    # Import each file into the internal DB under a temporary source name,
    # collect all tables, then export — and clean up after.
    import uuid
    from core.importer_csv import import_csv, import_sql, import_txt, _looks_like_sql

    tmp_sources = []   # (tmp_name, tname_base)
    tables = []
    errors = []

    # Phase 1: import each file (each uses its own connection and commits)
    for p in paths:
        p = p.strip()
        if not p or not os.path.exists(p):
            errors.append(f"not found: {p}")
            continue
        tmp_name = f"__batch_{uuid.uuid4().hex[:8]}"
        ext = os.path.splitext(p)[1].lower()
        tname_base = os.path.splitext(os.path.basename(p))[0]
        try:
            if ext == '.txt':
                import_txt(p, source_name=tmp_name)
            elif ext == '.sql' and _looks_like_sql(p):
                import_sql(p, source_name=tmp_name)
            else:
                import_csv(p, source_name=tmp_name)
        except Exception as e:
            errors.append(f"{os.path.basename(p)}: {e}")
            continue
        tmp_sources.append((tmp_name, tname_base))

    # Phase 2: read all imported data into tables list, then clean up
    conn = get_conn()
    for tmp_name, tname_base in tmp_sources:
        row = conn.execute("SELECT id FROM sources WHERE name=?", (tmp_name,)).fetchone()
        if not row:
            continue
        source_id = row["id"]
        table_rows = conn.execute(
            "SELECT DISTINCT table_name FROM records WHERE source_id=?", (source_id,)
        ).fetchall()
        for tr in table_rows:
            orig_tname = tr["table_name"]
            display_tname = tname_base if len(table_rows) == 1 else f"{tname_base}_{orig_tname}"
            recs = conn.execute(
                "SELECT data FROM records WHERE source_id=? AND table_name=?",
                (source_id, orig_tname)
            ).fetchall()
            records = [json.loads(r["data"]) for r in recs]
            fields_set = []
            for rec in records:
                for k in rec:
                    if k not in fields_set:
                        fields_set.append(k)
            tables.append({"name": display_tname, "fields": fields_set, "records": records})

    # Phase 3: clean up all temporary sources
    for tmp_name, _ in tmp_sources:
        row = conn.execute("SELECT id FROM sources WHERE name=?", (tmp_name,)).fetchone()
        if row:
            conn.execute("DELETE FROM records WHERE source_id=?", (row["id"],))
            conn.execute("DELETE FROM fields  WHERE source_id=?", (row["id"],))
            conn.execute("DELETE FROM sources WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()

    if not tables:
        return jsonify({"error": "No data imported", "details": errors}), 400

    try:
        stats = write_cronos(tables, output_dir, db_name=db_name)
        stats["errors"] = errors
        return jsonify({"ok": True, "stats": stats})
    except Exception as e:
        return jsonify({"error": str(e), "details": errors}), 500


@app.get('/api/cronos/preview')
def api_cronos_preview():
    """Parse a Cronos DB folder and return schema + first 50 records per table (no DB write)."""
    db_dir = request.args.get('path', '').strip()
    crack  = request.args.get('crack', 'false').lower() == 'true'
    if not db_dir or not os.path.isdir(db_dir):
        return jsonify({"error": "invalid path"}), 400
    parsed = parse_database(db_dir, crack=crack)
    # Trim records to first 50 for preview
    for t in parsed.get("tables", []):
        t["record_count"] = len(t["records"])
        t["records"] = t["records"][:50]
    return jsonify(parsed)


if __name__ == '__main__':
    app.run(debug=True, port=5055, use_reloader=False, threaded=True)
