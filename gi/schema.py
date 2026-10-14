"""Send the shape, not the rows (Chapter 6, Rung 2).

profile() reads the database once and builds a *schema card*: tables, columns,
types, row counts, null rates and distinct counts. It holds no data values.
The card is what the model sees. A person reviews and approves the data
classes before the card is used (Chapter 22: human approval at onboarding).
"""
import json
import sqlite3


def profile(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    card = {}
    for t in tables:
        n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        cols = []
        for _, name, ctype, *_ in conn.execute(f'PRAGMA table_info("{t}")'):
            nulls, distinct = conn.execute(
                f'SELECT SUM("{name}" IS NULL), COUNT(DISTINCT "{name}") FROM "{t}"').fetchone()
            cols.append({
                "name": name,
                "type": ctype,
                "null_rate": round((nulls or 0) / n, 3) if n else 0.0,
                "distinct": distinct,
            })
        card[t] = {"rows": n, "columns": cols}
    return card


def load_classes(path):
    """Data classes, approved by a person. Format:
    {"restricted": {"customers.name": "PERSON", ...}, "approved_by": "...", "approved_on": "..."}"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def card_for_model(card, classes):
    """The text the model sees: shape only, with the class label on each column."""
    restricted = {k.lower() for k in classes.get("restricted", {})}
    lines = []
    for t, info in card.items():
        lines.append(f"table {t} ({info['rows']} rows)")
        for c in info["columns"]:
            label = "RESTRICTED" if f"{t}.{c['name']}".lower() in restricted else "internal"
            lines.append(f"  - {c['name']} {c['type']} [{label}] null_rate={c['null_rate']} distinct={c['distinct']}")
    return "\n".join(lines)


def save_card(card, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2)


if __name__ == "__main__":
    import sys
    conn = sqlite3.connect(sys.argv[1])
    print(json.dumps(profile(conn), indent=2))
