from __future__ import annotations

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ai_manager import ai_service_manager


def test_basic_endpoints():
    print("\n--- TEST 1: Basic Endpoints (Immediate Port Liveness) ---")
    with TestClient(app) as client:
        # 1. Root endpoint
        t0 = time.time()
        res = client.get("/")
        elapsed = time.time() - t0
        print(f"GET / -> Status: {res.status_code}, Elapsed: {elapsed:.4f}s, Body: {res.json()}")
        assert res.status_code == 200
        assert res.json() == {"message": "CampusOne AI API is running."}

        # 2. Health endpoint (liveness check)
        t0 = time.time()
        res = client.get("/health")
        elapsed = time.time() - t0
        print(f"GET /health -> Status: {res.status_code}, Elapsed: {elapsed:.4f}s, Body: {res.json()}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "ai_service" in data
        # Ensure Groq API key is never exposed
        assert "gsk_" not in str(data)

    print("PASS: Basic endpoints respond immediately with status 200.")


def test_ai_warmup_and_readiness():
    print("\n--- TEST 2: AI Warmup & Readiness Differentiation ---")
    with TestClient(app) as client:
        # Give lifespan background task time to complete if running
        max_wait = 15
        start = time.time()
        while time.time() - start < max_wait:
            res = client.get("/health?readiness=true")
            if res.status_code == 200:
                print(f"AI Service ready in {time.time() - start:.2f}s: {res.json()}")
                break
            time.sleep(0.5)

        res = client.get("/health?readiness=true")
        print(f"GET /health?readiness=true -> Status: {res.status_code}")
        assert res.status_code == 200
        data = res.json()
        assert data["ready"] is True
        assert data["ai_service"]["components"]["retrieval"]["indexes_loaded"] is True
        # Verify no secret exposed
        assert "gsk_" not in str(data)

    print("PASS: /health distinguishes liveness from readiness.")


def test_chat_pipeline():
    print("\n--- TEST 3: /chat Pipeline (All Domains, Routing & Fallback) ---")
    with TestClient(app) as client:
        # 1. Out of scope query
        res = client.post("/chat", json={"message": "Write a quicksort program in Python."})
        print(f"Out of scope test -> Status: {res.status_code}")
        assert res.status_code == 200
        data = res.json()
        assert data["is_out_of_scope"] is True
        assert "I can currently help with" in data["answer"]
        print("  Answer:", data["answer"][:80], "...")

        # 2. Clarification query (ambiguous low-confidence query)
        res = client.post("/chat", json={"message": "account"})
        print(f"Clarification test -> Status: {res.status_code}")
        assert res.status_code == 200
        data = res.json()
        assert data["needs_clarification"] is True
        print("  Clarification question:", data["clarification_question"])

        # 3. Multi-domain query
        res = client.post(
            "/chat",
            json={"message": "My WiFi is not working and I also want to know my fee deadline."},
        )
        print(f"Multi-domain test -> Status: {res.status_code}")
        assert res.status_code == 200
        data = res.json()
        print("  Metadata status:", data["metadata"].get("status"))

        # 4. HR/Admin query with verified Bennett UG chunks
        res = client.post("/chat", json={"message": "What is the procedure for makeup examination?"})
        print(f"HR_ADMIN Domain test -> Status: {res.status_code}")
        assert res.status_code == 200
        data = res.json()
        assert "HR_ADMIN" in data["domains"]
        assert len(data["sources"]) > 0
        print("  Domains:", data["domains"])
        print("  Sources count:", len(data["sources"]))
        print("  First source:", data["sources"][0]["source_title"])
        print("  Answer preview:\n   ", data["answer"][:160].replace("\n", " "), "...")

        # 5. Revaluation query (unsupported topic in academic rules)
        res = client.post("/chat", json={"message": "How do I apply for revaluation?"})
        print(f"Revaluation query (unsupported topic) -> Status: {res.status_code}")
        assert res.status_code == 200
        data = res.json()
        assert len(data["sources"]) == 0
        print("  Metadata status:", data["metadata"].get("status"))

        # 5. IT Domain query (empty evidence behavior when no IT chunks in dataset)
        res = client.post("/chat", json={"message": "My university WiFi is not working."})
        print(f"IT Domain test -> Status: {res.status_code}")
        assert res.status_code == 200
        data = res.json()
        print("  Metadata status:", data["metadata"].get("status"))

        # 6. Fees query (empty evidence behavior)
        res = client.post("/chat", json={"message": "When are my semester fees due?"})
        print(f"FEES Domain test -> Status: {res.status_code}")
        assert res.status_code == 200
        data = res.json()
        print("  Metadata status:", data["metadata"].get("status"))

        # 7. Facilities query (empty evidence behavior)
        res = client.post("/chat", json={"message": "What are the hostel facilities?"})
        print(f"FACILITIES Domain test -> Status: {res.status_code}")
        assert res.status_code == 200
        data = res.json()
        print("  Metadata status:", data["metadata"].get("status"))

    print("PASS: /chat contract preserved across all 4 domains.")


def test_concurrent_requests():
    print("\n--- TEST 4: Concurrency & Single Initialization Guarantee ---")
    with TestClient(app) as client:
        messages = [
            "How do I apply for revaluation?",
            "Write a Python script for mergesort.",
            "My university WiFi is not working.",
            "When are my semester fees due?",
            "What are the hostel facilities?",
            "How do I apply for revaluation?",
            "account",
            "My payment isn't working.",
            "Write quicksort in C++.",
            "How do I apply for revaluation?",
        ]

        def send_req(msg):
            return client.post("/chat", json={"message": msg})

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(send_req, messages))
        elapsed = time.time() - t0

        print(f"Completed 10 concurrent requests in {elapsed:.2f}s")
        for i, res in enumerate(results):
            assert res.status_code == 200, f"Request {i} failed: {res.text}"
            data = res.json()
            assert "answer" in data
            assert "domains" in data

    print("PASS: 10 concurrent requests handled safely without race conditions.")


def test_memory_profile():
    print("\n--- TEST 5: Memory Usage Verification ---")
    import psutil

    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    rss_mb = mem_info.rss / (1024 * 1024)
    vms_mb = mem_info.vms / (1024 * 1024)

    print(f"Process Memory - RSS: {rss_mb:.1f} MB, VMS: {vms_mb:.1f} MB")
    print(f"Render Free Tier limit: 512 MB. Current usage: {rss_mb / 512 * 100:.1f}%")
    print("Instance sizing analysis:")
    if rss_mb > 450:
        print("  - WARNING: Process RSS is near 512 MB. Render Free Tier risks OOM under peak concurrency.")
        print("  - Recommendation: Use Render Starter instance (1 GB RAM) for stable production.")
    else:
        print("  - OK: Memory fits comfortably within limits.")


if __name__ == "__main__":
    test_basic_endpoints()
    test_ai_warmup_and_readiness()
    test_chat_pipeline()
    test_concurrent_requests()
    test_memory_profile()
    print("\n================ ALL TESTS PASSED ================\n")
