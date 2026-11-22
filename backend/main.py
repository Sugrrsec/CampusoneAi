from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from groq import RateLimitError

from backend.rag.retrieval.retriever import SUPPORTED_DOMAINS
from backend.schemas.api import (
    ChatRequest,
    ChatResponse,
    SourceReference,
)
from backend.services.ai_manager import ai_service_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan manager.

    Kicks off AI service warmup as an asynchronous background task so Uvicorn
    can bind to Render's $PORT in < 200 ms without waiting for PyTorch/FAISS.
    """
    init_task = asyncio.create_task(ai_service_manager.initialize())
    yield
    if not init_task.done():
        init_task.cancel()


app = FastAPI(
    title="CampusOne AI",
    description=(
        "One Front Door for Everything — "
        "University Student Assistant API"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------
# Core components & backward compatibility
# -------------------------------------------------------------------

retrieval_service = ai_service_manager.retrieval_service
intent_router = ai_service_manager.intent_router


def __getattr__(name: str) -> Any:
    """Allow lazy access to module-level singletons for backward compatibility."""
    if name == "domain_agents":
        return ai_service_manager.domain_agents
    if name == "retrieval_service":
        return ai_service_manager.retrieval_service
    if name == "intent_router":
        return ai_service_manager.intent_router
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def normalize_sources(
    agent_sources: list[dict[str, Any]],
    retrieved_knowledge: list[dict[str, Any]],
    domain: str,
) -> list[SourceReference]:
    """
    Convert domain agent sources into the common API format.

    Only sources that can be matched to actual retrieved knowledge
    are returned.
    """

    normalized: list[SourceReference] = []

    for source in agent_sources:
        document_name = source.get(
            "document_name",
            "",
        )

        page = source.get("page")

        section = source.get(
            "section"
        )

        source_url = source.get(
            "source_url"
        )

        for retrieved in retrieved_knowledge:
            retrieved_title = retrieved.get(
                "source_title",
                "",
            )

            retrieved_page = retrieved.get(
                "page"
            )

            retrieved_url = retrieved.get(
                "source_url"
            )

            title_matches = (
                not document_name
                or document_name == retrieved_title
            )

            page_matches = (
                page is None
                or retrieved_page is None
                or page == retrieved_page
            )

            url_matches = (
                not source_url
                or not retrieved_url
                or source_url == retrieved_url
            )

            if not (
                title_matches
                and page_matches
                and url_matches
            ):
                continue

            chunk_id = str(
                retrieved.get(
                    "chunk_id",
                    f"{domain}_{len(normalized) + 1}",
                )
            )

            chunk_score = retrieved.get("score")
            if chunk_score is not None and chunk_score > 1.0:
                chunk_score = round(min(chunk_score / 15.0, 1.0), 4)

            normalized.append(
                SourceReference(
                    chunk_id=chunk_id,
                    domain=domain,
                    source_title=retrieved_title,
                    page=retrieved_page,
                    score=chunk_score,
                    source_url=retrieved_url,
                )
            )

            break

    # Remove accidental duplicate sources.
    unique_sources: list[SourceReference] = []
    seen: set[tuple] = set()

    for source in normalized:
        key = (
            source.chunk_id,
            source.page,
            source.source_url,
        )

        if key in seen:
            continue

        seen.add(key)
        unique_sources.append(source)

    return unique_sources


def empty_evidence_response(
    session_id: str | None,
) -> ChatResponse:
    """
    Response returned when retrieval found no usable evidence.
    """

    return ChatResponse(
        answer=(
            "I don't have enough verified university information "
            "to answer that reliably yet."
        ),
        domains=[],
        confidence=0.0,
        needs_clarification=False,
        clarification_question=None,
        is_out_of_scope=False,
        sources=[],
        session_id=session_id,
        metadata={
            "status": "no_retrieved_evidence",
        },
    )


# -------------------------------------------------------------------
# Basic endpoints
# -------------------------------------------------------------------

@app.get("/")
async def root() -> dict[str, str]:
    """Basic root endpoint for liveness."""
    return {
        "message": "CampusOne AI API is running."
    }


@app.get("/health")
async def health(readiness: bool = False) -> Any:
    """
    Health-check endpoint.

    Distinguishes basic server liveness from full AI readiness:
    - Default (readiness=False): Returns HTTP 200 immediately once Uvicorn binds,
      allowing Render's port scan / liveness check to pass in < 1 second.
    - readiness=True: Returns HTTP 200 only if AI components are loaded;
      otherwise returns HTTP 503 for orchestrator readiness gates.
    """
    health_data = ai_service_manager.get_health_status()
    is_ready = ai_service_manager.is_ready

    if readiness and not is_ready:
        return JSONResponse(
            status_code=503,
            content={
                "status": "initializing",
                "ready": False,
                "ai_service": health_data,
            },
        )

    return {
        "status": "ok",
        "ready": is_ready,
        "ai_service": health_data,
    }


# -------------------------------------------------------------------
# Main chat endpoint
# -------------------------------------------------------------------

@app.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
) -> ChatResponse:
    """
    Main CampusOne AI pipeline.

    Flow:
        0. Ensure AI service initialization (waits safely if in progress).
        1. Route question.
        2. Handle clarification/out-of-scope.
        3. Retrieve domain-specific knowledge.
        4. Send retrieved evidence to domain agent(s) (with grounded fallback).
        5. Return grounded answer + sources.
    """

    try:
        # -----------------------------------------------------------
        # 0. ENSURE AI INITIALIZATION
        # -----------------------------------------------------------
        try:
            await ai_service_manager.ensure_ready()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"CampusOne AI service is currently unavailable: {exc}",
            ) from exc

        # -----------------------------------------------------------
        # 1. MEMBER 1 — ROUTING
        # -----------------------------------------------------------

        route_result = ai_service_manager.intent_router.route(
            request.message
        )

        # -----------------------------------------------------------
        # 2. OUT-OF-SCOPE
        # -----------------------------------------------------------

        if route_result.is_out_of_scope:
            return ChatResponse(
                answer=(
                    "I can currently help with university IT, "
                    "academic and administrative matters, fees, "
                    "and campus facilities/services."
                ),
                domains=[],
                confidence=route_result.confidence,
                needs_clarification=False,
                clarification_question=None,
                is_out_of_scope=True,
                sources=[],
                session_id=request.session_id,
                metadata={
                    "routing_method": (
                        route_result.routing_method
                    ),
                    "intent": route_result.intent,
                    "status": "out_of_scope",
                },
            )

        # -----------------------------------------------------------
        # 3. CLARIFICATION
        # -----------------------------------------------------------

        if route_result.needs_clarification:
            return ChatResponse(
                answer=(
                    route_result.clarification_question
                    or "Could you please clarify your request?"
                ),
                domains=route_result.domains,
                confidence=route_result.confidence,
                needs_clarification=True,
                clarification_question=(
                    route_result.clarification_question
                ),
                is_out_of_scope=False,
                sources=[],
                session_id=request.session_id,
                metadata={
                    "routing_method": (
                        route_result.routing_method
                    ),
                    "intent": route_result.intent,
                    "status": "needs_clarification",
                },
            )

        # -----------------------------------------------------------
        # 4. MEMBER 3 — RETRIEVAL
        # -----------------------------------------------------------

        retrieved_results = ai_service_manager.retrieval_service.retrieve_for_route(
            query=request.message,
            route_result=route_result,
            top_k=5,
        )

        if not retrieved_results:
            return empty_evidence_response(
                session_id=request.session_id
            )

        # -----------------------------------------------------------
        # 5. MEMBER 4 — DOMAIN AGENT(S)
        # -----------------------------------------------------------

        conversation_context: list[dict[str, str]] = []

        final_answers: list[str] = []
        final_sources: list[SourceReference] = []
        agent_confidences: dict[str, float | None] = {}

        for domain in route_result.domains:
            domain_results = [
                result
                for result in retrieved_results
                if result.get(
                    "retrieved_domain"
                ) == domain
            ]

            if not domain_results:
                continue

            agent = ai_service_manager.domain_agents.get(domain)

            if agent is not None:
                agent_result = agent.generate_answer(
                    question=request.message,
                    retrieved_knowledge=domain_results,
                    conversation_context=conversation_context,
                )
                answer_text = agent_result.answer.strip()
                agent_conf = agent_result.confidence
                raw_sources = agent_result.sources
            else:
                # Grounded fallback when Groq LLM agent is not configured
                snippets = [
                    r.get("text", "").strip()
                    for r in domain_results
                    if r.get("text")
                ]
                answer_text = (
                    f"Information regarding {domain}:\n" + "\n\n".join(snippets[:2])
                    if snippets
                    else "No specific details found in university records."
                )
                agent_conf = 0.8
                raw_sources = [
                    {
                        "document_name": r.get("source_title", ""),
                        "page": r.get("page"),
                        "section": None,
                        "source_url": r.get("source_url"),
                    }
                    for r in domain_results
                ]

            if answer_text:
                if len(route_result.domains) > 1:
                    final_answers.append(
                        f"{domain}: {answer_text}"
                    )
                else:
                    final_answers.append(
                        answer_text
                    )

            agent_confidences[domain] = agent_conf

            normalized = normalize_sources(
                agent_sources=raw_sources,
                retrieved_knowledge=domain_results,
                domain=domain,
            )

            final_sources.extend(
                normalized
            )

        # -----------------------------------------------------------
        # 6. FINAL RESPONSE
        # -----------------------------------------------------------

        if not final_answers:
            return empty_evidence_response(
                session_id=request.session_id
            )

        # Remove duplicate sources across domains.
        unique_sources: list[SourceReference] = []
        seen_sources: set[tuple] = set()

        for source in final_sources:
            key = (
                source.chunk_id,
                source.page,
                source.source_url,
            )

            if key in seen_sources:
                continue

            seen_sources.add(key)
            unique_sources.append(source)

        return ChatResponse(
            answer="\n\n".join(final_answers),
            domains=route_result.domains,
            confidence=route_result.confidence,
            needs_clarification=False,
            clarification_question=None,
            is_out_of_scope=False,
            sources=unique_sources,
            session_id=request.session_id,
            metadata={
                "routing_method": (
                    route_result.routing_method
                ),
                "intent": route_result.intent,
                "agent_confidences": agent_confidences,
                "retrieved_chunks": len(
                    retrieved_results
                ),
                "status": "answered",
            },
        )

    except RateLimitError:
        return ChatResponse(
            answer=(
                "The AI service is temporarily busy. "
                "Please try again shortly."
            ),
            domains=[],
            confidence=0.0,
            needs_clarification=False,
            clarification_question=None,
            is_out_of_scope=False,
            sources=[],
            session_id=request.session_id,
            metadata={
                "status": "provider_rate_limited",
                "provider": "groq",
            },
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "CampusOne AI could not process the request. "
                f"Error type: {type(exc).__name__}."
            ),
        ) from exc
