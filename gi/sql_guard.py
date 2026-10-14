"""Read-only SQL for model-written queries (Chapters 12 and 22).

Three walls, from weakest to strongest:

1. check_statement(): reads the SQL text and allows one SELECT (or WITH ... SELECT).
2. An SQLite authorizer: the database engine itself refuses anything that is not
   a read, and refuses restricted columns unless a person approved them.
3. A read-only connection: even if both checks above had a bug, the file is
   opened in read-only mode, so nothing can be written.

The model never sees the database connection. It only proposes text.
"""
import re
import sqlite3
import time

# Words that have no place in a read-only question.
FORBIDDEN = {
    "insert", "update", "delete", "drop", "create", "alter", "attach", "detach",
    "pragma", "replace", "vacuum", "reindex", "analyze", "begin", "commit",
    "rollback", "savepoint", "release", "into", "load_extension", "trigger",
}

# Functions a reporting query may call. Everything else is refused.
ALLOWED_FUNCTIONS = {
    "count", "sum", "avg", "min", "max", "total", "round", "abs", "coalesce",
    "ifnull", "nullif", "lower", "upper", "length", "substr", "trim", "printf",
    "date", "time", "datetime", "julianday", "strftime", "group_concat", "iif",
    "cast", "like", "glob", "instr",
}


# Action codes from the SQLite C API. Older Python versions do not export all of
# them as constants, so the numbers are given here.
SQLITE_READ = getattr(sqlite3, "SQLITE_READ", 20)
SQLITE_SELECT = getattr(sqlite3, "SQLITE_SELECT", 21)
SQLITE_FUNCTION = getattr(sqlite3, "SQLITE_FUNCTION", 31)
SQLITE_RECURSIVE = getattr(sqlite3, "SQLITE_RECURSIVE", 33)


class SqlRejected(Exception):
    """The query was refused. `reason` is safe to log: it never holds data."""

    def __init__(self, reason, detail=""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class NeedsApproval(Exception):
    """The query reads restricted columns. A person must approve it first."""

    def __init__(self, columns):
        super().__init__("needs human approval for: " + ", ".join(sorted(columns)))
        self.columns = sorted(columns)


_STRING = re.compile(r"'(?:[^']|'')*'")
_IDENT = re.compile(r'"(?:[^"]|"")*"|\[[^\]]*\]|`[^`]*`')
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _strip_literals(sql):
    """Remove comments, strings and quoted names, so keywords hidden in them
    cannot fool the word check (and harmless words in strings do not block)."""
    s = _BLOCK_COMMENT.sub(" ", sql)
    s = _LINE_COMMENT.sub(" ", s)
    s = _STRING.sub(" '' ", s)
    s = _IDENT.sub(" _q_ ", s)
    return s


def check_statement(sql):
    """Wall 1. Raise SqlRejected unless `sql` is exactly one read-only query."""
    if not sql or not sql.strip():
        raise SqlRejected("empty_query")
    if len(sql) > 5000:
        raise SqlRejected("query_too_long")
    bare = _strip_literals(sql).strip()
    bare = bare.rstrip(";").strip()
    if ";" in bare:
        raise SqlRejected("more_than_one_statement")
    words = re.findall(r"[a-z_]+", bare.lower())
    if not words or words[0] not in ("select", "with"):
        raise SqlRejected("not_a_select")
    bad = sorted(set(words) & FORBIDDEN)
    if bad:
        raise SqlRejected("forbidden_keyword", ",".join(bad))
    # Return the original text (literals intact), without the trailing semicolon.
    return sql.strip().rstrip(";").strip()


def open_read_only(path):
    """Wall 3. Open the database file so that it cannot be changed."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def run_query(conn, sql, restricted=(), approved=(), max_rows=200, timeout_s=5.0):
    """Run one checked query with all three walls in place.

    restricted: names like "customers.email" that need approval to read.
    approved:   restricted names a person has approved for this query.
    Returns (columns, rows, truncated, read_restricted).
    read_restricted: the approved restricted columns the query actually read.
    """
    clean = check_statement(sql)
    restricted = {c.lower() for c in restricted}
    approved = {c.lower() for c in approved}
    refused_columns, refused_actions, read_restricted = set(), [], set()

    def authorizer(action, arg1, arg2, dbname, source):
        if action == SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == SQLITE_READ:
            name = f"{arg1}.{arg2}".lower()
            if name in restricted:
                if name not in approved:
                    refused_columns.add(name)
                    return sqlite3.SQLITE_DENY
                read_restricted.add(name)
            return sqlite3.SQLITE_OK
        if action == SQLITE_FUNCTION:
            if (arg2 or "").lower() in ALLOWED_FUNCTIONS:
                return sqlite3.SQLITE_OK
            refused_actions.append(f"function:{arg2}")
            return sqlite3.SQLITE_DENY
        if action == SQLITE_RECURSIVE:
            return sqlite3.SQLITE_OK
        refused_actions.append(f"action:{action}")
        return sqlite3.SQLITE_DENY

    deadline = time.monotonic() + timeout_s

    def watchdog():
        return 1 if time.monotonic() > deadline else 0  # non-zero stops the query

    conn.set_authorizer(authorizer)
    conn.set_progress_handler(watchdog, 10_000)
    try:
        cur = conn.execute(f"SELECT * FROM (\n{clean}\n) LIMIT {int(max_rows) + 1}")
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
    except sqlite3.DatabaseError as e:
        if refused_columns:
            raise NeedsApproval(refused_columns) from None
        if refused_actions:
            raise SqlRejected("refused_by_database", ",".join(refused_actions)) from None
        if "interrupted" in str(e).lower():
            raise SqlRejected("timeout") from None
        raise SqlRejected("database_error", type(e).__name__) from None
    finally:
        conn.set_authorizer(None)
        conn.set_progress_handler(None, 0)
    truncated = len(rows) > max_rows
    return columns, rows[:max_rows], truncated, sorted(read_restricted)
