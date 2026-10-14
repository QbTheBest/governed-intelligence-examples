"""Model adapters.

Every step names the model it uses (Chapter 4: model per step). Two adapters:

* ScriptedModel: a stand-in that needs no API key and no GPU. It answers the
  questions in examples/golden.json and refuses everything else. It exists so
  that the pipeline, the checks and the tests run anywhere. It is not AI.
* OpenAICompatibleModel: any server that speaks the common "chat completions"
  format. That includes local servers (Ollama, vLLM, LM Studio, llama.cpp) and
  many hosted providers. Configure it with environment variables:
      GI_MODEL_BASE_URL   e.g. http://localhost:11434/v1
      GI_MODEL_NAME       e.g. qwen3:8b
      GI_MODEL_API_KEY    optional
"""
import json
import os
import re
import urllib.request


class Model:
    name = "abstract"

    def complete(self, task, system, user):
        raise NotImplementedError


def extract_json(text):
    """Models often wrap JSON in prose or code fences. Take the first object."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


def _norm(q):
    return re.sub(r"[^a-z0-9 ]", "", q.lower()).strip()


class ScriptedModel(Model):
    name = "scripted-stand-in"

    def __init__(self, golden_path):
        with open(golden_path, encoding="utf-8") as f:
            cases = json.load(f)
        self.known = {_norm(c["question"]): c for c in cases if c.get("sql")}

    def _question(self, user):
        m = re.search(r"<question_[0-9a-f]+>\s*(.*?)\s*</question_[0-9a-f]+>", user, re.S)
        return m.group(1) if m else ""

    def complete(self, task, system, user):
        if task == "route":
            q = _norm(self._question(user))
            return json.dumps({"route": "lookup" if q in self.known else "off_topic"})
        if task == "write_sql":
            case = self.known.get(_norm(self._question(user)))
            if not case:
                return json.dumps({"sql": None, "explanation": "I cannot answer this from the schema."})
            return json.dumps({"sql": case["sql"], "explanation": case.get("explanation", "")})
        if task == "explain":
            m = re.search(r"<result>\s*(\{.*?\})\s*</result>", user, re.S)
            data = json.loads(m.group(1))
            cols, rows = data["columns"], data["rows"]
            if not rows:
                return json.dumps({"insight": "The query returned no rows."})
            first = ", ".join(f"{c} = {v}" for c, v in zip(cols, rows[0]))
            text = f"The query returned {len(rows)} row(s). The first row is: {first}."
            return json.dumps({"insight": text})
        raise ValueError(task)


class OpenAICompatibleModel(Model):
    def __init__(self, base_url=None, model=None, api_key=None, timeout=60):
        base_url = base_url or os.environ.get("GI_MODEL_BASE_URL")
        model = model or os.environ.get("GI_MODEL_NAME")
        if not base_url or not model:
            raise SystemExit("Set GI_MODEL_BASE_URL and GI_MODEL_NAME first, "
                             "for example http://localhost:11434/v1 and qwen3:8b.")
        self.base_url = base_url.rstrip("/")
        self.name = model
        self.api_key = api_key if api_key is not None else os.environ.get("GI_MODEL_API_KEY", "")
        self.timeout = timeout

    def complete(self, task, system, user):
        body = json.dumps({
            "model": self.name,
            "temperature": 0,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        if self.api_key:
            req.add_header("Authorization", "Bearer " + self.api_key)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            reply = json.load(r)
        return reply["choices"][0]["message"]["content"]
