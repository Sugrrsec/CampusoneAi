from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .bm25 import BM25Index


SUPPORTED_DOMAINS = (
    "IT",
    "HR_ADMIN",
    "FEES",
    "FACILITIES",
)

# Minimum relevance threshold: genuine keyword matches score >= 0.5,
# while completely absent topics (e.g. WiFi on academic docs or revaluation) score 0.0.
DEFAULT_MIN_SCORE = 0.5


class DomainRetriever:
    """
    Domain-aware BM25 retrieval layer for CampusOne AI.

    Maintains one BM25 store for each supported domain.
    Replaces runtime SentenceTransformers + FAISS with zero-dependency Okapi BM25,
    reducing memory usage from ~600 MB to < 1 MB to fit within Render Free's 512 MB limit.
    """

    def __init__(
        self,
        embedding_service: Any = None,
    ) -> None:
        # embedding_service is kept as an optional parameter for backward compatibility
        self.embedding_service = embedding_service
        self.stores: dict[str, BM25Index] = {
            domain: BM25Index()
            for domain in SUPPORTED_DOMAINS
        }

    def build(
        self,
        documents: Sequence[dict[str, Any]],
    ) -> None:
        """
        Build domain-specific BM25 stores.

        Each document must contain:
            - domain
            - text

        Other metadata fields are preserved.
        """
        grouped_documents: dict[str, list[dict[str, Any]]] = {
            domain: []
            for domain in SUPPORTED_DOMAINS
        }

        for document in documents:
            domain = document.get("domain")
            text = document.get("text")

            if domain not in SUPPORTED_DOMAINS:
                raise ValueError(
                    f"Unsupported domain: {domain}"
                )

            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    "Every document must contain non-empty text."
                )

            grouped_documents[domain].append(
                dict(document)
            )

        for domain, domain_documents in grouped_documents.items():
            self.stores[domain].fit(domain_documents)

    def retrieve(
        self,
        query: str,
        domains: Sequence[str],
        top_k: int = 5,
        min_score: float = DEFAULT_MIN_SCORE,
    ) -> list[dict[str, Any]]:
        """
        Retrieve the most relevant chunks from requested domains using BM25 ranking.

        Results below min_score are discarded to avoid returning unrelated chunks.
        Multiple domains are supported for multi-topic questions.
        """
        if not query.strip():
            raise ValueError(
                "Query cannot be empty."
            )

        if top_k <= 0:
            raise ValueError(
                "top_k must be greater than 0."
            )

        if min_score < 0.0:
            raise ValueError(
                "min_score must be non-negative."
            )

        if not domains:
            return []

        invalid_domains = [
            domain
            for domain in domains
            if domain not in SUPPORTED_DOMAINS
        ]

        if invalid_domains:
            raise ValueError(
                f"Unsupported domains: {invalid_domains}"
            )

        results: list[dict[str, Any]] = []

        for domain in domains:
            store = self.stores[domain]
            domain_results = store.search(
                query=query,
                top_k=top_k,
                min_score=min_score,
            )

            for result in domain_results:
                result["retrieved_domain"] = domain
                results.append(result)

        results.sort(
            key=lambda item: item.get("score", 0.0),
            reverse=True,
        )

        return results[:top_k]

    def size(
        self,
        domain: str,
    ) -> int:
        """Return the number of chunks stored for a domain."""
        if domain not in SUPPORTED_DOMAINS:
            raise ValueError(
                f"Unsupported domain: {domain}"
            )
        return self.stores[domain].size

    def save(
        self,
        directory: str | Path,
    ) -> None:
        """Save all domain-specific document stores to disk as JSON."""
        directory = Path(directory)
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        for domain, store in self.stores.items():
            domain_directory = directory / domain
            domain_directory.mkdir(parents=True, exist_ok=True)
            store.save(domain_directory / "documents.json")

    @classmethod
    def load(
        cls,
        directory: str | Path,
        embedding_service: Any = None,
    ) -> "DomainRetriever":
        """Load previously saved domain-specific document stores from disk."""
        directory = Path(directory)

        if not directory.exists():
            raise FileNotFoundError(
                f"Retriever directory not found: {directory}"
            )

        retriever = cls(
            embedding_service=embedding_service
        )

        for domain in SUPPORTED_DOMAINS:
            domain_directory = directory / domain
            doc_path = domain_directory / "documents.json"
            meta_path = domain_directory / "metadata.json"

            if doc_path.exists():
                retriever.stores[domain] = BM25Index.load(doc_path)
            elif meta_path.exists():
                # Compatibility with existing metadata files
                retriever.stores[domain] = BM25Index.load(meta_path)

        return retriever


__all__ = [
    "DomainRetriever",
    "SUPPORTED_DOMAINS",
    "DEFAULT_MIN_SCORE",
]
