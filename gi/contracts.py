"""Check the environment first (Chapters 19 and 21).

Plain rules, run in code before any answer is written. If a rule fails, the
honest answer is "do not trust today's data", and it goes first.
"""

RULES = [
    ("every_invoice_has_a_line",
     "SELECT COUNT(*) FROM invoices i WHERE NOT EXISTS "
     "(SELECT 1 FROM invoice_lines l WHERE l.invoice_id = i.id)"),
    ("no_negative_quantities",
     "SELECT COUNT(*) FROM invoice_lines WHERE quantity < 0"),
    ("invoice_total_matches_lines",
     "SELECT COUNT(*) FROM invoices i WHERE ABS(i.total - "
     "(SELECT COALESCE(SUM(l.quantity * l.unit_price), 0) FROM invoice_lines l WHERE l.invoice_id = i.id)) > 0.01"),
]


def check(conn):
    """Return a list of (rule, failing_count). An empty list means all rules pass."""
    failures = []
    for name, sql in RULES:
        n = conn.execute(sql).fetchone()[0]
        if n:
            failures.append((name, n))
    return failures
