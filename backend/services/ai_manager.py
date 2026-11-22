from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any

from backend.agents.groq_agent import GroqDomainAgent
from backend.rag.retrieval.retriever import SUPPORTED_DOMAINS
from backend.rag.retrieval.service import RetrievalService
from backend.router.router import IntentRouter

logger = logging.getLogger("campusone.ai_manager")

CHUNK_FILE = Path("data/processed/scset_ug_chunks.jsonl")
VECTOR_STORE_PATH = Path("data/processed/vector_stores")


class AIServiceManager:
    """
    Manages thread-safe and async-safe lifecycle of CampusOne AI services.

    Prevents startup bottlenecks by:
    1. Avoiding eager module-level model downloads or index building.
    2. Providing background / lazy initialization so the HTTP server can bind to $PORT immediately.
    3. Preventing concurrent requests from triggering duplicate initialization.
    4. Explicitly tracking status and health of retrieval, router, and domain agents.
    """

    def __init__(
        self,
        chunk_file: Path | str = CHUNK_FILE,
        vector_store_path: Path | str = VECTOR_STORE_PATH,
    ) -> None:
        self.chunk_file = Path(chunk_file)
        self.vector_store_path = Path(vector_store_path)

        self._sync_lock = threading.Lock()
        self._async_lock: asyncio.Lock | None = None
        self._init_task: asyncio.Task | None = None

        self.status: str = "uninitialized"  # "uninitialized", "initializing", "ready", "degraded", "failed"
        self.error: str | None = None

        self.retrieval_status: str = "uninitialized"
        self.router_status: str = "uninitialized"
        self.agents_status: str = "uninitialized"

        # Core components
        self.retrieval_service = RetrievalService(
            vector_store_path=self.vector_store_path
        )
        self.intent_router = IntentRouter()
        self.domain_agents: dict[str, GroqDomainAgent] = {}

    @property
    def is_ready(self) -> bool:
        """Return True if AI services are ready to process queries (including degraded fallback)."""
        return self.status in ("ready", "degraded")

    def _get_async_lock(self) -> asyncio.Lock:
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    async def initialize(self) -> None:
        """
        Asynchronously initialize AI services without blocking the FastAPI event loop.
        Guarantees that multiple concurrent callers wait on the same initialization.
        """
        if self.is_ready:
            return

        lock = self._get_async_lock()
        async with lock:
            if self.is_ready:
                return

            self.status = "initializing"
            self.error = None

            try:
                # Offload heavy CPU / disk / network operations to worker thread
                await asyncio.to_thread(self._sync_initialize)
            except Exception as exc:
                self.status = "failed"
                self.error = f"{type(exc).__name__}: {str(exc)}"
                logger.error("AI service initialization failed: %s", self.error, exc_info=True)
                raise

    def _sync_initialize(self) -> None:
        """Synchronously initialize components (executed in worker thread)."""
        with self._sync_lock:
            # 1. Initialize Intent Router
            try:
                # If GROQ_API_KEY is available, IntentRouter uses Groq LLM; otherwise keyword fallback
                groq_key = os.getenv("GROQ_API_KEY")
                self.intent_router = IntentRouter(api_key=groq_key)
                self.router_status = "ready"
            except Exception as exc:
                self.router_status = f"failed: {type(exc).__name__}"
                logger.warning("IntentRouter init warning: %s", exc)

            # 2. Initialize Retrieval Service & FAISS Indexes
            try:
                self.retrieval_service.ensure_initialized(chunk_file=self.chunk_file)
                self.retrieval_status = "ready"
            except Exception as exc:
                self.retrieval_status = f"failed: {type(exc).__name__}: {str(exc)}"
                self.status = "failed"
                self.error = f"Retrieval initialization failed: {exc}"
                raise

            # 3. Initialize Domain Agents
            groq_key = os.getenv("GROQ_API_KEY")
            if groq_key:
                try:
                    model = os.getenv("GROQ_ROUTER_MODEL", "openai/gpt-oss-20b")
                    self.domain_agents = {
                        domain: GroqDomainAgent(
                            domain=domain,
                            api_key=groq_key,
                            model=model,
                        )
                        for domain in SUPPORTED_DOMAINS
                    }
                    self.agents_status = "ready"
                except Exception as exc:
                    self.agents_status = f"failed: {type(exc).__name__}: {str(exc)}"
                    logger.warning("Domain agents init warning: %s", exc)
            else:
                self.domain_agents = {}
                self.agents_status = "not_configured (GROQ_API_KEY missing)"
                logger.info("GROQ_API_KEY not set. Operating with retrieval + grounded fallback.")

            # Set overall status
            if self.retrieval_status == "ready" and self.agents_status == "ready":
                self.status = "ready"
            elif self.retrieval_status == "ready":
                self.status = "degraded"
            else:
                self.status = "failed"

    async def ensure_ready(self) -> None:
        """
        Ensure services are ready before handling a request.
        If uninitialized, initiates initialization. If initializing, waits for completion.
        """
        if self.is_ready:
            return

        if self.status == "failed":
            # Retry initialization once in case of transient failure
            logger.info("Attempting re-initialization after previous failure...")

        await self.initialize()

        if self.status == "failed":
            raise RuntimeError(f"AI service unavailable: {self.error}")

    def get_health_status(self) -> dict[str, Any]:
        """
        Returns structured health and readiness information.
        Does NOT expose any secrets or API keys.
        """
        return {
            "status": self.status,
            "ready": self.is_ready,
            "error": self.error,
            "components": {
                "retrieval": {
                    "status": self.retrieval_status,
                    "indexes_loaded": self.retrieval_service.is_loaded,
                },
                "router": {
                    "status": self.router_status,
                },
                "agents": {
                    "status": self.agents_status,
                    "configured_domains": list(self.domain_agents.keys()),
                    "groq_configured": bool(os.getenv("GROQ_API_KEY")),
                },
            },
        }


# Global singleton instance (components inside it load lazily)
ai_service_manager = AIServiceManager()
