"""Ask the demo database a question.

    python examples/run_chat.py "What was the total revenue in 2025?"
    python examples/run_chat.py "Who are the five customers with the highest revenue?"
    python examples/run_chat.py "Who are the five customers with the highest revenue?" --approve customers.name

By default it uses the scripted stand-in model (no API key needed). To use a
real model through an OpenAI-compatible server, for example a local Ollama:

    export GI_MODEL_BASE_URL=http://localhost:11434/v1
    export GI_MODEL_NAME=qwen3:8b
    python examples/run_chat.py "Which city brings the most revenue?" --model api
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from gi import chat, schema, sql_guard                      # noqa: E402
from gi.models import OpenAICompatibleModel, ScriptedModel  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--db", default=os.path.join(HERE, "demo.db"))
    ap.add_argument("--model", choices=["scripted", "api"], default="scripted")
    ap.add_argument("--approve", nargs="*", default=[], help="restricted columns a person approves")
    ap.add_argument("--save-trace", help="write the trace as JSON lines to this file")
    a = ap.parse_args()

    if not os.path.exists(a.db):
        sys.exit("No database yet. Run: python examples/make_demo_db.py")
    conn = sql_guard.open_read_only(a.db)
    classes = schema.load_classes(os.path.join(HERE, "data_classes.json"))
    card = schema.profile(conn)
    model = ScriptedModel(os.path.join(HERE, "golden.json")) if a.model == "scripted" else OpenAICompatibleModel()

    ans = chat.ask(a.question, conn, model, card, classes, approved=a.approve)

    print(f"\nStatus: {ans.status}")
    if ans.message:
        print(ans.message)
    if ans.sql:
        print(f"\nSQL proposed by the model:\n  {ans.sql}")
        if ans.explanation:
            print(f"What it computes: {ans.explanation}")
    if ans.rows:
        print("\nResult:")
        print("  " + " | ".join(ans.columns))
        for r in ans.rows[:20]:
            print("  " + " | ".join(str(v) for v in r))
    if ans.insight:
        print(f"\nInsight: {ans.insight}")
    for w in ans.warnings:
        print(f"Warning: {w}")
    print(f"\nTrace {ans.trace.run_id}: {len(ans.trace.entries)} steps, chain intact: {ans.trace.verify()}")
    for e in ans.trace.entries:
        ev = e["event"]
        extra = {k: v for k, v in ev.items() if k not in ("run_id", "step", "status", "t_ms")}
        print(f"  {ev['t_ms']:>5} ms  {ev['step']:<10} {ev['status']:<15} {extra}")
    if a.save_trace:
        ans.trace.save(a.save_trace)


if __name__ == "__main__":
    main()
