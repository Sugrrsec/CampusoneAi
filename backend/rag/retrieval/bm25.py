"""
Lightweight, pure Python BM25 (Okapi BM25) retrieval implementation for CampusOne AI.

Zero external ML dependencies (no PyTorch, no Transformers, no SentenceTransformers, no FAISS).
Memory footprint: < 1 MB.
Query latency: < 1 ms.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Stopwords & Tokenization
# ---------------------------------------------------------------------------

STANDARD_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can",
    "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't",
    "down", "during", "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have",
    "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", "him",
    "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't",
    "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor",
    "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out",
    "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some",
    "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to",
    "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's",
    "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've",
    "your", "yours", "yourself", "yourselves"
}

# Domain-specific terms that appear in virtually every document and dilute retrieval if unweighted
CORPUS_BOILERPLATE_STOPWORDS = {
    "university", "student", "students", "shall", "may", "following", "rules", "academic"
}

# Generic procedural queries that cause accidental single-token false positives
PROCEDURAL_STOPWORDS = {
    "apply", "connect", "working", "work", "procedure", "procedures",
    "tell", "help", "need", "want", "know", "please"
}

ALL_STOPWORDS = (
    STANDARD_STOPWORDS
    | CORPUS_BOILERPLATE_STOPWORDS
    | PROCEDURAL_STOPWORDS
)


class PorterStemmer:
    """
    Standard Porter Stemming Algorithm (Martin Porter 1980) in pure Python.
    No dependencies, handles inflectional variants (calculating -> calcul, examinations -> examin).
    """

    def __init__(self) -> None:
        self.b = ""
        self.k = 0
        self.k0 = 0
        self.j = 0

    def _cons(self, i: int) -> bool:
        if self.b[i] in "aeiou":
            return False
        if self.b[i] == "y":
            if i == self.k0:
                return True
            else:
                return not self._cons(i - 1)
        return True

    def _m(self) -> int:
        n = 0
        i = self.k0
        while True:
            if i > self.j:
                return n
            if not self._cons(i):
                break
            i += 1
        i += 1
        while True:
            while True:
                if i > self.j:
                    return n
                if self._cons(i):
                    break
                i += 1
            i += 1
            n += 1
            while True:
                if i > self.j:
                    return n
                if not self._cons(i):
                    break
                i += 1
            i += 1

    def _vowelinstem(self) -> bool:
        for i in range(self.k0, self.j + 1):
            if not self._cons(i):
                return True
        return False

    def _doublec(self, i: int) -> bool:
        if i < self.k0 + 1:
            return False
        if self.b[i] != self.b[i - 1]:
            return False
        return self._cons(i)

    def _cvc(self, i: int) -> bool:
        if i < self.k0 + 2 or not self._cons(i) or self._cons(i - 1) or not self._cons(i - 2):
            return False
        ch = self.b[i]
        if ch in "wxY":
            return False
        return True

    def _ends(self, s: str) -> bool:
        length = len(s)
        if s[length - 1] != self.b[self.k]:
            return False
        if length > self.k - self.k0 + 1:
            return False
        if self.b[self.k - length + 1 : self.k + 1] != s:
            return False
        self.j = self.k - length
        return True

    def _setto(self, s: str) -> None:
        length = len(s)
        self.b = self.b[: self.j + 1] + s + self.b[self.j + length + 1 :]
        self.k = self.j + length

    def _r(self, s: str) -> None:
        if self._m() > 0:
            self._setto(s)

    def _step1ab(self) -> None:
        if self.b[self.k] == "s":
            if self._ends("sses"):
                self.k -= 2
            elif self._ends("ies"):
                self._setto("i")
            elif self.b[self.k - 1] != "s":
                self.k -= 1
        if self._ends("eed"):
            if self._m() > 0:
                self.k -= 1
        elif (self._ends("ed") or self._ends("ing")) and self._vowelinstem():
            self.k = self.j
            if self._ends("at"):
                self._setto("ate")
            elif self._ends("bl"):
                self._setto("ble")
            elif self._ends("iz"):
                self._setto("ize")
            elif self._doublec(self.k):
                self.k -= 1
                ch = self.b[self.k]
                if ch in "lsz":
                    self.k += 1
            elif self._m() == 1 and self._cvc(self.k):
                self._setto("e")

    def _step1c(self) -> None:
        if self._ends("y") and self._vowelinstem():
            self.b = self.b[: self.k] + "i" + self.b[self.k + 1 :]

    def _step2(self) -> None:
        pairs = [
            ("ational", "ate"), ("tional", "tion"), ("enci", "ence"), ("anci", "ance"),
            ("izer", "ize"), ("bli", "ble"), ("alli", "al"), ("entli", "ent"),
            ("eli", "e"), ("ousli", "ous"), ("ization", "ize"), ("ation", "ate"),
            ("ator", "ate"), ("alism", "al"), ("iveness", "ive"), ("fulness", "ful"),
            ("ousness", "ous"), ("aliti", "al"), ("iviti", "ive"), ("biliti", "ble"),
        ]
        for suffix, repl in pairs:
            if self._ends(suffix):
                self._r(repl)
                break

    def _step3(self) -> None:
        pairs = [
            ("icate", "ic"), ("ative", ""), ("alize", "al"), ("iciti", "ic"),
            ("ical", "ic"), ("ful", ""), ("ness", ""),
        ]
        for suffix, repl in pairs:
            if self._ends(suffix):
                self._r(repl)
                break

    def _step4(self) -> None:
        suffixes = [
            "al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement",
            "ment", "ent", "ou", "ism", "ate", "iti", "ous", "ive", "ize",
        ]
        for suffix in suffixes:
            if self._ends(suffix):
                if self._m() > 1:
                    self.k = self.j
                return
        if self._ends("ion"):
            if self.j >= 0 and self.b[self.j] in "st" and self._m() > 1:
                self.k = self.j

    def _step5(self) -> None:
        self.j = self.k
        if self.b[self.k] == "e":
            a = self._m()
            if a > 1 or (a == 1 and not self._cvc(self.k - 1)):
                self.k -= 1
        if self.b[self.k] == "l" and self._doublec(self.k) and self._m() > 1:
            self.k -= 1

    def stem(self, p: str) -> str:
        p = p.lower()
        if len(p) < 3:
            return p
        self.b = p
        self.k = len(p) - 1
        self.k0 = 0
        self._step1ab()
        self._step1c()
        self._step2()
        self._step3()
        self._step4()
        self._step5()
        return self.b[self.k0 : self.k + 1]


_STEMMER = PorterStemmer()


def tokenize(text: str) -> list[str]:
    """
    Tokenize text into lowercase, stemmed terms with hyphens normalized.
    Filters out common and domain boilerplate stopwords.
    """
    if not text:
        return []

    text = text.lower()
    text = re.sub(r"\bwi-fi\b", "wifi", text)
    text = re.sub(r"\bmake-up\b", "makeup", text)

    words = re.findall(r"\b[a-z0-9]+(?:'[a-z]+)?\b", text)
    tokens: list[str] = []

    for w in words:
        if w in ALL_STOPWORDS or len(w) <= 1:
            continue
        stemmed = _STEMMER.stem(w)
        tokens.append(stemmed)

    return tokens


# ---------------------------------------------------------------------------
# BM25 Index
# ---------------------------------------------------------------------------

class BM25Index:
    """
    Fast, lightweight Okapi BM25 Index in pure Python.
    Designed for memory-constrained container environments (Render Free 512MB).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.documents: list[dict[str, Any]] = []
        self.doc_tokens: list[list[str]] = []
        self.doc_lengths: list[int] = []
        self.avg_dl: float = 0.0
        self.doc_freqs: Counter[str] = Counter()
        self.idf: dict[str, float] = {}

    @property
    def size(self) -> int:
        return len(self.documents)

    def fit(self, documents: Sequence[dict[str, Any]]) -> None:
        """Fit BM25 index on a sequence of document chunks."""
        self.documents = [dict(doc) for doc in documents]
        doc_count = len(self.documents)

        if doc_count == 0:
            self.doc_tokens = []
            self.doc_lengths = []
            self.avg_dl = 0.0
            self.doc_freqs = Counter()
            self.idf = {}
            return

        self.doc_tokens = []
        self.doc_lengths = []
        self.doc_freqs = Counter()

        total_tokens = 0
        for doc in self.documents:
            content = f"{doc.get('text', '')} {doc.get('source_title', '')}"
            tokens = tokenize(content)
            self.doc_tokens.append(tokens)
            length = len(tokens)
            self.doc_lengths.append(length)
            total_tokens += length
            for term in set(tokens):
                self.doc_freqs[term] += 1

        self.avg_dl = total_tokens / doc_count if doc_count > 0 else 0.0

        # Standard Okapi BM25 IDF with Laplace smoothing (+0.5)
        self.idf = {}
        for term, freq in self.doc_freqs.items():
            self.idf[term] = math.log(1.0 + (doc_count - freq + 0.5) / (freq + 0.5))

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 2.5,
    ) -> list[dict[str, Any]]:
        """
        Search the index using Okapi BM25 ranking.
        Results scoring below min_score are excluded to prevent hallucination.
        """
        if not self.documents:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        doc_count = len(self.documents)
        scores: list[float] = [0.0] * doc_count
        query_freqs = Counter(query_tokens)

        for term, qf in query_freqs.items():
            if term not in self.idf:
                continue
            idf_val = self.idf[term]
            for idx, d_tokens in enumerate(self.doc_tokens):
                tf = d_tokens.count(term)
                if tf > 0:
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (
                        1 - self.b + self.b * (self.doc_lengths[idx] / self.avg_dl)
                    )
                    scores[idx] += idf_val * (numerator / denominator)

        ranked_indices = sorted(
            range(doc_count),
            key=lambda i: scores[i],
            reverse=True,
        )

        results: list[dict[str, Any]] = []
        for idx in ranked_indices:
            raw_bm25 = scores[idx]
            if raw_bm25 < min_score:
                break
            doc = dict(self.documents[idx])
            # Normalized score [0.0, 1.0] for API schema compatibility (SourceReference.score le=1.0)
            norm_score = round(min(raw_bm25 / 15.0, 1.0), 4)
            doc["score"] = norm_score
            doc["bm25_score"] = round(raw_bm25, 4)
            doc["retrieval_method"] = "bm25"
            results.append(doc)
            if len(results) >= top_k:
                break

        return results

    def save(self, path: str | Path) -> None:
        """Persist documents to disk as JSON for caching/inspection."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(self.documents, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str | Path, k1: float = 1.5, b: float = 0.75) -> "BM25Index":
        """Load documents from JSON and fit index."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"BM25 index document file not found: {p}")
        with p.open("r", encoding="utf-8") as f:
            docs = json.load(f)
        index = cls(k1=k1, b=b)
        index.fit(docs)
        return index


__all__ = ["BM25Index", "tokenize", "PorterStemmer"]
