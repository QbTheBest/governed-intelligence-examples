"""Mask, check, call, restore (Chapter 7).

In the book, a local language model does the masking of free text. Here the
sensitive values are already known (they come from columns that a person
classified as Restricted), so masking is exact. The checker and the restore
step are the same as in the book.
"""
import re

PATTERNS = {
    "phone": re.compile(r"\b(?:\+?\d[\s-]?){9,13}\b"),
    "long_id": re.compile(r"\b\d{6,}\b"),
    "money": re.compile(r"[$€£]\s?\d[\d,]*(?:\.\d{2})?"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
}

PLACEHOLDER = re.compile(r"\[[A-Z_]+_\d+\]")


class Vault:
    """Maps placeholders to real values. Lives in memory, for one task only.
    It is never sent to a model and never written to a log."""

    def __init__(self):
        self._by_value = {}
        self._by_placeholder = {}
        self._counts = {}

    def placeholder(self, kind, value):
        key = (kind, str(value))
        if key not in self._by_value:
            n = self._counts.get(kind, 0) + 1
            self._counts[kind] = n
            p = f"[{kind}_{n}]"
            self._by_value[key] = p
            self._by_placeholder[p] = str(value)
        return self._by_value[key]

    def values(self):
        return list(self._by_placeholder.values())

    def items(self):
        return self._by_placeholder.items()

    def __contains__(self, placeholder):
        return placeholder in self._by_placeholder

    def __len__(self):
        return len(self._by_placeholder)


def mask_rows(columns, rows, kinds, vault):
    """Replace values in sensitive columns with typed, stable placeholders.

    kinds: {column_name: "PERSON" | "EMAIL" | "PHONE" | ...}
    The same real value always gets the same placeholder in one task.
    """
    idx = {i: kinds[c.lower()] for i, c in enumerate(columns) if c.lower() in kinds}
    out = []
    for row in rows:
        out.append(tuple(vault.placeholder(idx[i], v) if i in idx and v is not None else v
                         for i, v in enumerate(row)))
    return out


def vault_leak(text, vault):
    """True if any real value from the vault appears in the text."""
    lowered = text.lower()
    return any(v and str(v).lower() in lowered for v in vault.values())


def check_outbound(text, vault):
    """Return (ok, reasons). Never return the matched text itself."""
    reasons = []
    lowered = text.lower()
    for original in vault.values():
        if original and str(original).lower() in lowered:
            reasons.append("vault_value_present")
            break
    for name, rx in PATTERNS.items():
        if rx.search(text):
            reasons.append(name)
    return (not reasons), reasons


def restore(draft, vault):
    """Put the real values back. Report placeholders the vault does not know."""
    unknown = [p for p in PLACEHOLDER.findall(draft) if p not in vault]
    for placeholder, real in vault.items():
        draft = draft.replace(placeholder, str(real))
    return draft, unknown
