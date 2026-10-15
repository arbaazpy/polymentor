"""Inference-time grounding from each expert's local corpus.

The corpus that was aligned into the Nugen model is also kept in the repo, so at
answer time we retrieve the most relevant sections and hand them to the model
as authoritative notes. Retrieval is BM25 over heading-delimited sections: no
embedding service, no vector DB, deterministic and fast enough to run per call.

Sections whose titles match PINNED_TITLE_KEYWORDS (scope, abstention rules)
are always included so the model knows what it must refuse or delegate.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import cache

from apps.experts.fleet import get_spec

PINNED_TITLE_KEYWORDS = ("scope", "abstention")
DEFAULT_TOP_K = 3
DEFAULT_MAX_CHARS = 6000

STOPWORDS = frozenset(
    """
    a an and are as at be been but by can could do does for from had has have how i if in
    into is it its may me my not of on or our should so than that the their then there these
    they this to us was we were what when where which while who why will with would you your
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MD_HEADING = re.compile(r"^#{1,4}\s+(.+?)\s*$")
_UNDERLINE = re.compile(r"^[-=]{3,}$")


@dataclass(frozen=True)
class Section:
    source: str
    title: str
    text: str

    @property
    def ref(self) -> str:
        return f"{self.source}#{self.title}"


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    return [
        _stem(tok)
        for tok in _TOKEN_RE.findall(text.lower())
        if tok not in STOPWORDS and (len(tok) > 1 or tok.isdigit())
    ]


def split_sections(source: str, text: str) -> list[Section]:
    """Split markdown (`#` headings) or plain text (underlined headings) into sections."""
    lines = text.splitlines()
    sections: list[Section] = []
    title = "Preamble"
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append(Section(source=source, title=title, text=body))

    i = 0
    while i < len(lines):
        line = lines[i]
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        heading = _MD_HEADING.match(line)
        if heading:
            flush()
            title, buf = heading.group(1), []
        elif line.strip() and _UNDERLINE.match(next_line):
            flush()
            title, buf = line.strip(), []
            i += 1
        else:
            buf.append(line)
        i += 1
    flush()
    return sections


class CorpusIndex:
    """Okapi BM25 over corpus sections."""

    def __init__(self, sections: list[Section], k1: float = 1.5, b: float = 0.75):
        self.sections = sections
        self.k1, self.b = k1, b
        self.term_freqs = [Counter(tokenize(f"{s.title} {s.text}")) for s in sections]
        self.lengths = [sum(tf.values()) for tf in self.term_freqs]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        doc_freq: Counter[str] = Counter()
        for tf in self.term_freqs:
            doc_freq.update(tf.keys())
        n = len(sections)
        self.idf = {t: math.log(1 + (n - df + 0.5) / (df + 0.5)) for t, df in doc_freq.items()}

    def score(self, query_tokens: set[str], idx: int) -> float:
        tf, length = self.term_freqs[idx], self.lengths[idx]
        norm = self.k1 * (1 - self.b + self.b * length / self.avg_length)
        total = 0.0
        for term in query_tokens:
            freq = tf.get(term)
            if freq:
                total += self.idf[term] * freq * (self.k1 + 1) / (freq + norm)
        return total

    def search(self, query: str, k: int, exclude: set[int] | None = None) -> list[int]:
        query_tokens = set(tokenize(query))
        exclude = exclude or set()
        scored = [
            (self.score(query_tokens, i), i) for i in range(len(self.sections)) if i not in exclude
        ]
        scored = [pair for pair in scored if pair[0] > 0]
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [i for _, i in scored[:k]]


@cache
def get_index(expert_key: str) -> CorpusIndex:
    spec = get_spec(expert_key)
    sections: list[Section] = []
    for path in spec.corpus_paths:
        sections.extend(split_sections(path.name, path.read_text(encoding="utf-8")))
    return CorpusIndex(sections)


def retrieve(
    expert_key: str,
    query: str,
    *,
    k: int = DEFAULT_TOP_K,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Section]:
    """Top-k relevant sections plus the pinned scope/abstention sections."""
    index = get_index(expert_key)
    primary_source = get_spec(expert_key).corpus_paths[0].name
    pinned = [
        i
        for i, s in enumerate(index.sections)
        if s.source == primary_source and any(kw in s.title.lower() for kw in PINNED_TITLE_KEYWORDS)
    ]
    budget = max_chars - sum(len(index.sections[i].text) for i in pinned)
    chosen: list[int] = []
    for i in index.search(query, k=k, exclude=set(pinned)):
        size = len(index.sections[i].text)
        if chosen and size > budget:
            continue
        chosen.append(i)
        budget -= size
    return [index.sections[i] for i in chosen + pinned]
