"""Deterministic keyword / skill matching utilities.

These are plain-Python helpers (no LLM calls) used both as scoring inputs
and exposed as `function_tool`s so agents can ground their reasoning in
exact, reproducible matches instead of hallucinating overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"[A-Za-z0-9+#.\-]+")

# Common synonyms / aliases so "JS" matches "JavaScript", etc.
_ALIASES: dict[str, set[str]] = {
    "javascript": {"js", "javascript", "ecmascript"},
    "typescript": {"ts", "typescript"},
    "python": {"python", "py"},
    "postgresql": {"postgres", "postgresql", "psql"},
    "kubernetes": {"k8s", "kubernetes"},
    "amazon web services": {"aws", "amazon web services"},
    "google cloud platform": {"gcp", "google cloud platform", "google cloud"},
    "machine learning": {"ml", "machine learning"},
    "artificial intelligence": {"ai", "artificial intelligence"},
    "continuous integration": {"ci", "continuous integration"},
    "continuous deployment": {"cd", "continuous deployment"},
    "natural language processing": {"nlp", "natural language processing"},
    "user interface": {"ui", "user interface"},
    "user experience": {"ux", "user experience"},
    "restful api": {"rest", "restful", "rest api", "restful api"},
}


def _normalize(term: str) -> str:
    return term.strip().lower()


def _expand(term: str) -> set[str]:
    """Return all known aliases for a term, including itself."""
    normalized = _normalize(term)
    for canonical, aliases in _ALIASES.items():
        if normalized == canonical or normalized in aliases:
            return aliases | {canonical}
    return {normalized}


@dataclass
class MatchResult:
    matched: list[str]
    missing: list[str]

    @property
    def match_ratio(self) -> float:
        total = len(self.matched) + len(self.missing)
        if total == 0:
            return 100.0
        return round(100 * len(self.matched) / total, 2)


def tokenize(text: str) -> set[str]:
    """Lowercase word/token set for coarse substring-free matching."""
    return {t.lower() for t in _WORD_RE.findall(text)}


def text_contains_term(text: str, term: str) -> bool:
    """Check whether `term` (or a known alias) appears in `text`."""
    haystack = text.lower()
    for alias in _expand(term):
        if len(alias) <= 3:
            # Short terms (js, ml, ci...) must match as a whole word to avoid
            # false positives like "ml" inside "html".
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", haystack):
                return True
        elif alias in haystack:
            return True
    return False


def match_terms(resume_text: str, terms: list[str]) -> MatchResult:
    """Match a list of required/preferred terms against resume text."""
    matched, missing = [], []
    for term in terms:
        if not term or not term.strip():
            continue
        if text_contains_term(resume_text, term):
            matched.append(term)
        else:
            missing.append(term)
    return MatchResult(matched=matched, missing=missing)


# Weak, overused action verbs an ATS-optimized resume should avoid opening bullets with.
WEAK_ACTION_VERBS = {
    "responsible for",
    "worked on",
    "helped with",
    "involved in",
    "duties included",
    "assisted",
    "tasked with",
    "handled",
    "in charge of",
    "participated in",
}

STRONG_ACTION_VERBS = {
    "achieved", "architected", "automated", "built", "delivered", "designed",
    "drove", "engineered", "improved", "increased", "launched", "led",
    "optimized", "orchestrated", "reduced", "resolved", "scaled", "shipped",
    "spearheaded", "streamlined", "transformed",
}


def find_weak_verbs(bullet: str) -> list[str]:
    lowered = bullet.lower().strip()
    return [phrase for phrase in WEAK_ACTION_VERBS if lowered.startswith(phrase)]


def starts_with_strong_verb(bullet: str) -> bool:
    first_word = bullet.strip().split(" ")[0].lower().strip(".,;:")
    return first_word in STRONG_ACTION_VERBS


def has_quantified_result(bullet: str) -> bool:
    """Heuristic: does the bullet contain a number / percentage / metric?"""
    return bool(re.search(r"\d", bullet))
