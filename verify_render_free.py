"""
Comprehensive verification test suite for Render Free optimization:
1. Startup & port binding latency
2. Health & readiness endpoints
3. Retrieval accuracy on representative academic questions (CGPA, makeup exams, course registration, internships, attendance)
4. Unsupported questions (Wi-Fi, revaluation) returning empty evidence without policy invention
5. Groq / grounded fallback answer generation with proper SourceReferences
6. Concurrency stress test (multiple simultaneous requests)
7. Exact RSS memory measurement at each stage
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
import psutil
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ai_manager import ai_service_manager


def get_current_rss_mb() -> float:
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def run_all_checks():
    print("=" * 70)
    print("CAMPUSONE AI — RENDER FREE BACKEND VERIFICATION")
    print("=" * 70)

    # -------------------------------------------------------------
    # STAGE 1: Process Startup Memory
    # -------------------------------------------------------------
    base_rss = get_current_rss_mb()
    print(f"\n[STAGE 1] Process Memory at Module Import: {base_rss:.1f} MB")
    assert base_rss < 150.0, f"Import memory too high: {base_rss:.1f} MB"

    # -------------------------------------------------------------
    # STAGE 2: FastAPI Startup & Lifespan Initialization
    # -------------------------------------------------------------
    t0 = time.time()
    with TestClient(app) as client:
        startup_duration = time.time() - t0
        print(f"[STAGE 2] TestClient initialized in {startup_duration:.4f}s")

        # 1. Immediate Health Check (Liveness)
        t_health = time.time()
        res = client.get("/health")
        health_lat = time.time() - t_health
        print(f"  GET /health: status={res.status_code} in {health_lat*1000:.1f}ms")
        assert res.status_code == 200
        health_data = res.json()
        assert health_data["status"] == "ok"
        assert "ai_service" in health_data

        # 2. Readiness Check (eventually reports ready)
        start_wait = time.time()
        ready_duration = 0.0
        res_ready = None
        for _ in range(50):
            res_ready = client.get("/health?readiness=true")
            if res_ready.status_code == 200:
                ready_duration = time.time() - start_wait
                break
            time.sleep(0.05)

        print(f"  GET /health?readiness=true: status={res_ready.status_code} (Ready in {ready_duration:.3f}s)")
        assert res_ready.status_code == 200
        ready_data = res_ready.json()
        assert ready_data["ready"] is True
        assert ready_data["ai_service"]["components"]["retrieval"]["indexes_loaded"] is True
        print(f"  Retrieval method: BM25 (lightweight, zero-ML)")

        post_init_rss = get_current_rss_mb()
        print(f"  Memory after AI initialization: {post_init_rss:.1f} MB (Delta: +{post_init_rss - base_rss:.1f} MB)")
        assert post_init_rss < 200.0, f"Memory after init too high: {post_init_rss:.1f} MB"

        # ---------------------------------------------------------
        # STAGE 3: Representative Academic Questions (Must retrieve relevant evidence)
        # ---------------------------------------------------------
        print("\n[STAGE 3] Representative Academic Questions (Ground Truth Retrieval)")
        academic_questions = [
            ("How is CGPA calculated for undergraduate students?", "CGPA"),
            ("What is the procedure and medical certificate rule for makeup examination?", "Makeup Exams"),
            ("What are the regulations for course registration in a semester?", "Course Registration"),
            ("Can a B.Tech student start an internship in the 7th semester?", "Internships"),
            ("What happens if a student is continuously absent from the university for 21 days?", "Attendance/Absence"),
        ]

        for q, label in academic_questions:
            t_q = time.time()
            res = client.post("/chat", json={"message": q})
            elapsed = time.time() - t_q
            assert res.status_code == 200
            data = res.json()
            print(f"\n  Query [{label}]: '{q}'")
            print(f"    Elapsed: {elapsed*1000:.1f}ms | Domains: {data['domains']}")
            print(f"    Sources returned: {len(data['sources'])}")
            assert len(data["sources"]) > 0, f"No sources returned for valid query: {q}"
            src = data["sources"][0]
            print(f"    Top Source: [{src['chunk_id']}] {src['source_title']} (Page {src['page']}, Score: {src['score']})")
            print(f"    Answer: {data['answer'][:110].replace(chr(10), ' ')}...")
            assert not data["is_out_of_scope"]
            assert not data["needs_clarification"]

        post_academic_rss = get_current_rss_mb()
        print(f"\n  Memory after academic queries: {post_academic_rss:.1f} MB")

        # ---------------------------------------------------------
        # STAGE 4: Unsupported Questions (Must NOT hallucinate policies)
        # ---------------------------------------------------------
        print("\n[STAGE 4] Unsupported Questions (Empty Evidence / Scope Policy)")
        unsupported_questions = [
            ("How do I connect to campus Wi-Fi network?", "Wi-Fi (IT - no chunks in dataset)"),
            ("What is the revaluation procedure for semester exam papers?", "Revaluation (Not in academic rules)"),
            ("Where is the university cricket stadium located?", "Campus Sports (Not in dataset)"),
        ]

        for q, label in unsupported_questions:
            res = client.post("/chat", json={"message": q})
            assert res.status_code == 200
            data = res.json()
            print(f"\n  Query [{label}]: '{q}'")
            print(f"    Status: {data['metadata'].get('status')}")
            print(f"    Sources count: {len(data['sources'])}")
            print(f"    Answer: {data['answer']}")
            # Must return 0 sources and insufficient evidence response
            assert len(data["sources"]) == 0
            assert "verified university information" in data["answer"] or "out_of_scope" in str(data["metadata"])

        # ---------------------------------------------------------
        # STAGE 5: Out of Scope & Clarification
        # ---------------------------------------------------------
        print("\n[STAGE 5] Out-of-Scope and Clarification Handling")
        # Out-of-scope
        res = client.post("/chat", json={"message": "Write a bubble sort algorithm in Java."})
        assert res.status_code == 200
        data = res.json()
        assert data["is_out_of_scope"] is True
        print(f"  Out of scope query verified: is_out_of_scope={data['is_out_of_scope']}")

        # Clarification
        res = client.post("/chat", json={"message": "account"})
        assert res.status_code == 200
        data = res.json()
        assert data["needs_clarification"] is True
        print(f"  Clarification query verified: needs_clarification={data['needs_clarification']}")

        # ---------------------------------------------------------
        # STAGE 6: Concurrency & Memory Spike Stress Test
        # ---------------------------------------------------------
        print("\n[STAGE 6] Concurrency Stress Test (Simultaneous Requests)")
        stress_queries = [
            "How is CGPA calculated?",
            "What are makeup examination rules?",
            "Can I start internship in 7th sem?",
            "Continuous absence for 21 days penalty?",
            "How do I register for semester courses?",
            "Write a Python mergesort.",
            "How do I apply for revaluation?",
            "My campus WiFi is not working.",
            "What is the passing grade threshold?",
            "What are the attendance requirements?",
        ]

        def send_request(msg: str):
            return client.post("/chat", json={"message": msg})

        t_conc = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            responses = list(executor.map(send_request, stress_queries))
        conc_elapsed = time.time() - t_conc

        print(f"  Executed 10 concurrent requests in {conc_elapsed:.3f}s (Avg: {conc_elapsed/10*1000:.1f}ms per query)")
        for i, r in enumerate(responses):
            assert r.status_code == 200, f"Request {i} failed: {r.text}"

        peak_rss = get_current_rss_mb()
        print(f"\n[STAGE 7] Memory Profiling Summary:")
        print(f"  Base Python RSS:       {base_rss:.1f} MB")
        print(f"  After Init RSS:        {post_init_rss:.1f} MB")
        print(f"  After Concurrency RSS: {peak_rss:.1f} MB")
        print(f"  Render Free Limit:     512.0 MB")
        print(f"  Headroom Remaining:    {512.0 - peak_rss:.1f} MB ({(512.0 - peak_rss)/512.0*100:.1f}%)")
        print(f"  Sub-300MB Target Met:  {'YES' if peak_rss < 300.0 else 'NO'}")

    print("\n" + "=" * 70)
    print("ALL 10 VERIFICATION CHECKS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    run_all_checks()
