import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples"))

from gi import privacy, sizing, sql_guard, stats  # noqa: E402
from gi.trace import Trace                          # noqa: E402
import make_demo_db                                 # noqa: E402

RESTRICTED = ["customers.name", "customers.email", "customers.phone"]


class Db(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "t.db")
        make_demo_db.build(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.conn = sql_guard.open_read_only(self.path)

    def tearDown(self):
        self.conn.close()


class TestStatementCheck(unittest.TestCase):
    def rejects(self, sql, reason):
        with self.assertRaises(sql_guard.SqlRejected) as cm:
            sql_guard.check_statement(sql)
        self.assertEqual(cm.exception.reason, reason)

    def test_plain_select_passes(self):
        sql_guard.check_statement("SELECT COUNT(*) FROM invoices;")

    def test_with_passes(self):
        sql_guard.check_statement("WITH t AS (SELECT 1 AS x) SELECT x FROM t")

    def test_write_statements_are_refused(self):
        self.rejects("DELETE FROM customers", "not_a_select")
        self.rejects("UPDATE customers SET name = 'x'", "not_a_select")
        self.rejects("DROP TABLE customers", "not_a_select")

    def test_second_statement_is_refused(self):
        self.rejects("SELECT 1; DROP TABLE customers", "more_than_one_statement")

    def test_keyword_inside_a_select_is_refused(self):
        self.rejects("SELECT * INTO backup FROM customers", "forbidden_keyword")

    def test_words_inside_strings_do_not_block(self):
        sql_guard.check_statement("SELECT 'please drop by' AS note")

    def test_semicolon_inside_string_is_not_a_second_statement(self):
        sql_guard.check_statement("SELECT 'a;b' AS x")

    def test_hidden_in_comment_does_not_matter(self):
        sql_guard.check_statement("SELECT 1 /* ; DROP TABLE x */")


class TestRunQuery(Db):
    def test_aggregate_runs(self):
        cols, rows, truncated, read = sql_guard.run_query(
            self.conn, "SELECT COUNT(*) AS n FROM invoices", RESTRICTED)
        self.assertEqual(rows[0][0], 600)
        self.assertEqual(read, [])

    def test_restricted_column_needs_approval(self):
        with self.assertRaises(sql_guard.NeedsApproval) as cm:
            sql_guard.run_query(self.conn, "SELECT email FROM customers", RESTRICTED)
        self.assertEqual(cm.exception.columns, ["customers.email"])

    def test_renaming_a_column_does_not_hide_it(self):
        with self.assertRaises(sql_guard.NeedsApproval):
            sql_guard.run_query(self.conn, "SELECT c.name AS who FROM customers c", RESTRICTED)

    def test_approved_column_runs_and_is_reported(self):
        _, rows, _, read = sql_guard.run_query(
            self.conn, "SELECT name FROM customers", RESTRICTED, approved=["customers.name"])
        self.assertEqual(len(rows), 40)
        self.assertEqual(read, ["customers.name"])

    def test_unknown_function_is_refused_by_the_database(self):
        with self.assertRaises(sql_guard.SqlRejected) as cm:
            sql_guard.run_query(self.conn, "SELECT randomblob(8)", RESTRICTED)
        self.assertEqual(cm.exception.reason, "refused_by_database")

    def test_row_limit(self):
        _, rows, truncated, _ = sql_guard.run_query(
            self.conn, "SELECT id FROM invoices", RESTRICTED, max_rows=10)
        self.assertEqual(len(rows), 10)
        self.assertTrue(truncated)

    def test_read_only_connection_is_the_last_wall(self):
        # Even if every check above had a bug, the file cannot be changed.
        with self.assertRaises(sqlite3.OperationalError):
            self.conn.execute("DELETE FROM customers")


class TestPrivacy(unittest.TestCase):
    def test_placeholders_are_typed_and_stable(self):
        v = privacy.Vault()
        rows = privacy.mask_rows(["name", "total"], [("Ada Testoglu", 10), ("Ada Testoglu", 5)],
                                 {"name": "PERSON"}, v)
        self.assertEqual(rows, [("[PERSON_1]", 10), ("[PERSON_1]", 5)])

    def test_check_blocks_patterns_and_vault_values(self):
        v = privacy.Vault()
        v.placeholder("PERSON", "Ada Testoglu")
        self.assertFalse(privacy.check_outbound("call +90 555 123 4567", v)[0])
        self.assertFalse(privacy.check_outbound("mail ada@example.invalid", v)[0])
        ok, reasons = privacy.check_outbound("Dear Ada Testoglu", v)
        self.assertFalse(ok)
        self.assertEqual(reasons, ["vault_value_present"])
        self.assertTrue(privacy.check_outbound("Dear [PERSON_1]", v)[0])

    def test_restore_reports_unknown_placeholders(self):
        v = privacy.Vault()
        v.placeholder("PERSON", "Ada Testoglu")
        text, unknown = privacy.restore("[PERSON_1] and [PERSON_7]", v)
        self.assertEqual(text, "Ada Testoglu and [PERSON_7]")
        self.assertEqual(unknown, ["[PERSON_7]"])


class TestTraceStatsSizing(unittest.TestCase):
    def test_tampering_breaks_the_chain(self):
        t = Trace()
        t.log("a", "OK", rows=1)
        t.log("b", "OK", rows=2)
        self.assertTrue(t.verify())
        t.entries[0]["event"]["rows"] = 99
        self.assertFalse(t.verify())

    def test_wilson_matches_the_book(self):
        lo, hi = stats.wilson(20, 20)
        self.assertAlmostEqual(lo, 0.84, places=2)
        self.assertEqual(hi, 1.0)

    def test_sizing_matches_chapter_5(self):
        r = sizing.plan(32, 4.5, 64, 8, 128, 32768, 1)
        self.assertAlmostEqual(r["kv_cache_gb"], 8.6, places=1)
        self.assertGreater(r["total_gb"], 24)      # a 24 GB card cannot hold it


if __name__ == "__main__":
    unittest.main()
