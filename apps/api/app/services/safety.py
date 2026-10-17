"""Backend-enforced safety notices for assistant replies.

The "human review needed" note is added by the backend from the user's message
and the reply, not left to the model, so it appears even if the model forgets.
Keyword matching over-triggers on purpose: a spare note is cheaper than a missing one.
"""

from __future__ import annotations

import re

_TOPICS: dict[str, re.Pattern[str]] = {
    "financial": re.compile(
        r"\b(invest\w*|stocks?|shares?|crypto\w*|bitcoin|loans?|mortgage|tax(es)?|retirement|"
        r"portfolio|trading|debt|insurance|budget\w*|salary)\b",
        re.IGNORECASE,
    ),
    "legal": re.compile(
        r"\b(legal\w*|lawsuit|sue|court|lawyer|attorney|contract|visa|immigration|copyright|"
        r"liabilit\w+|divorce|tenant|landlord|gdpr)\b",
        re.IGNORECASE,
    ),
    "medical": re.compile(
        r"\b(medical|medicines?|medication|symptoms?|diagnos\w*|doctor|dosage|dose|pain|"
        r"treatment|disease|illness|pregnan\w*|allerg\w*|mental health|therapy|prescription)\b",
        re.IGNORECASE,
    ),
    "security": re.compile(
        r"\b(vulnerab\w*|breach\w*|hack\w*|malware|ransomware|phishing|exploit\w*|incident|"
        r"compromised|cve-\d+|security patch|leaked (?:password|key|credentials?))\b",
        re.IGNORECASE,
    ),
}

_LABELS = {"financial": "financial", "legal": "legal", "medical": "medical", "security": "security remediation"}


def review_topics(*texts: str) -> list[str]:
    combined = "\n".join(texts)
    return [topic for topic, pattern in _TOPICS.items() if pattern.search(combined)]


def review_note(topics: list[str]) -> str | None:
    if not topics:
        return None
    named = ", ".join(_LABELS[t] for t in topics)
    return (
        f"Human review needed: this touches on {named} matters. Treat the reply as general information, "
        "not professional advice, and check with a qualified person before acting on it."
    )
