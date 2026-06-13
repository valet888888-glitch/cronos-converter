"""
Cross-database search engine.
"""
import json
from .db import get_conn


def search(query: str, limit: int = 200) -> list:
    """Full-text search across all sources. Returns list of result dicts."""
    conn = get_conn()

    # FTS search
    rows = conn.execute("""
        SELECT r.id, r.source_id, r.table_name, r.rec_id, r.data,
               s.name AS source_name, s.type AS source_type
        FROM records_fts f
        JOIN records r ON r.id = f.rowid
        JOIN sources s ON s.id = r.source_id
        WHERE records_fts MATCH ?
        LIMIT ?
    """, (query, limit)).fetchall()

    results = []
    for row in rows:
        results.append({
            "id":          row["id"],
            "source_id":   row["source_id"],
            "source_name": row["source_name"],
            "source_type": row["source_type"],
            "table_name":  row["table_name"],
            "rec_id":      row["rec_id"],
            "data":        json.loads(row["data"]),
        })
    conn.close()
    return results


def search_cross(query: str, limit: int = 500) -> dict:
    """
    Cross-search: find records in ALL sources that share any field value
    with the initial query results. Returns graph data (nodes + edges).
    """
    initial = search(query, limit=limit)
    if not initial:
        return {"nodes": [], "edges": [], "results": []}

    # Collect candidate values (phone, email, name tokens)
    candidate_values = set()
    for rec in initial:
        for k, v in rec["data"].items():
            if v and isinstance(v, str) and len(v) > 3:
                candidate_values.add(v.strip())

    # Search for each value across all sources
    conn = get_conn()
    related = {}
    for val in list(candidate_values)[:50]:  # cap to avoid explosion
        try:
            rows = conn.execute("""
                SELECT r.id, r.source_id, r.table_name, r.rec_id, r.data,
                       s.name AS source_name
                FROM records_fts f
                JOIN records r ON r.id = f.rowid
                JOIN sources s ON s.id = r.source_id
                WHERE records_fts MATCH ?
                LIMIT 20
            """, (json.dumps(val)[1:-1],)).fetchall()
            for row in rows:
                if row["id"] not in related:
                    related[row["id"]] = {
                        "id": row["id"],
                        "source_id": row["source_id"],
                        "source_name": row["source_name"],
                        "table_name": row["table_name"],
                        "data": json.loads(row["data"]),
                        "matched_on": val,
                    }
        except Exception:
            pass

    conn.close()

    # Build graph nodes and edges
    nodes = []
    edges = []
    seen_ids = set()

    for rec in initial:
        node_id = f"r_{rec['id']}"
        if node_id not in seen_ids:
            nodes.append({"id": node_id, "label": rec["source_name"],
                          "group": rec["source_name"], "data": rec["data"]})
            seen_ids.add(node_id)

    for rec in related.values():
        node_id = f"r_{rec['id']}"
        if node_id not in seen_ids:
            nodes.append({"id": node_id, "label": rec["source_name"],
                          "group": rec["source_name"], "data": rec["data"]})
            seen_ids.add(node_id)

        # Edge: connect to initial records that share the matched value (no self-loops)
        for init_rec in initial:
            if f"r_{init_rec['id']}" == node_id:
                continue
            if any(str(v).strip() == rec["matched_on"]
                   for v in init_rec["data"].values()):
                edges.append({
                    "from": f"r_{init_rec['id']}",
                    "to":   node_id,
                    "label": rec["matched_on"][:30],
                })

    return {
        "nodes":   nodes,
        "edges":   edges,
        "results": initial,
        "related": list(related.values()),
    }


def list_sources() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT s.id, s.name, s.type, s.path, s.imported_at, COUNT(r.id) AS record_count "
        "FROM sources s LEFT JOIN records r ON r.source_id=s.id "
        "GROUP BY s.id ORDER BY s.imported_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
