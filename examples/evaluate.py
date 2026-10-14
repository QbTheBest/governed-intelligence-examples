"""Run the golden set and report an honest pass rate (Chapters 17 and 18).

For answerable questions, the pipeline's result is compared with an
independent reference query. For attacks and off-topic questions, the
expected status is checked: a model that follows an injection but a gate
that blocks it is a pass.

    python examples/evaluate.py
    python examples/evaluate.py --model api
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from gi import chat, schema, sql_guard                      # noqa: E402
from gi.models import OpenAICompatibleModel, ScriptedModel  # noqa: E402
from gi.stats import wilson                                 # noqa: E402


def same_result(rows_a, rows_b):
    def norm(rows):
        return sorted(tuple(round(v, 2) if isinstance(v, float) else v for v in r) for r in rows)
    return norm(rows_a) == norm(rows_b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "demo.db"))
    ap.add_argument("--model", choices=["scripted", "api"], default="scripted")
    a = ap.parse_args()

    golden_path = os.path.join(HERE, "golden.json")
    cases = json.load(open(golden_path, encoding="utf-8"))
    conn = sql_guard.open_read_only(a.db)
    truth = sql_guard.open_read_only(a.db)    # a separate connection for reference queries
    classes = schema.load_classes(os.path.join(HERE, "data_classes.json"))
    card = schema.profile(conn)
    model = ScriptedModel(golden_path) if a.model == "scripted" else OpenAICompatibleModel()

    passed = 0
    for c in cases:
        approve = c.get("approve", [])
        ans = chat.ask(c["question"], conn, model, card, classes)
        ok = ans.status == c["expect_status"]
        note = ans.status
        if ok and approve:
            ans = chat.ask(c["question"], conn, model, card, classes, approved=approve)
            ok = ans.status == c.get("expect_status_after_approval", "SUCCESS")
            note += f" -> approved -> {ans.status}"
        if ok and ans.status == "SUCCESS" and c.get("reference_sql"):
            ref = truth.execute(c["reference_sql"]).fetchall()
            ok = same_result(ans.rows, ref)
            note += ", matches reference" if ok else ", DIFFERS from reference"
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {c['id']}  {note}")

    n = len(cases)
    lo, hi = wilson(passed, n)
    print(f"\n{passed} of {n} passed. 95% range for the true pass rate: {lo:.0%} to {hi:.0%}.")
    print("A small set like this cannot prove high quality (Chapter 17). Add cases from real failures.")


if __name__ == "__main__":
    main()
