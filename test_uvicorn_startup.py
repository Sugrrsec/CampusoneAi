import subprocess
import sys
import time
import urllib.request
import json

PORT = 8765

print(f"Testing Render start command on port {PORT}...")
cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", str(PORT)]

t0 = time.time()
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

bound = False
response_data = None
elapsed = 0

try:
    for attempt in range(50):
        time.sleep(0.1)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    elapsed = time.time() - t0
                    response_data = json.loads(resp.read().decode())
                    bound = True
                    break
        except Exception:
            continue

    if bound:
        print(f"SUCCESS: Server bound to port {PORT} and responded 200 in {elapsed:.3f} seconds!")
        print(f"Health response: {response_data}")
    else:
        print("FAILED to bind to port within timeout")
finally:
    proc.terminate()
    proc.wait(timeout=5)

assert bound, "Server failed to bind"
