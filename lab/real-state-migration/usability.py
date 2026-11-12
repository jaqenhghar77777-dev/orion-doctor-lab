"""Bounded stock-runtime probes. Row values and application output stay private."""
import json
import os
import signal
import subprocess
import time
from urllib.request import urlopen

MAIN = "agents/main/agent/openclaw-agent.sqlite"
EXPECTED = {"session_entry_snapshots": (4, 3), "session_nodes": (9, 9), "session_windows": (10, 10)}


def allow_strict(report, rc):
    if report["result"] == "PASS":
        return rc == 0 and report["failures"] == []
    failures = report["failures"]
    return (rc == 1 and report["result"] == "STOP" and bool(failures) and
            all(f.get("database") == MAIN and f.get("code") == "LOGICAL_RECORD_MISMATCH"
                and EXPECTED.get(f.get("table")) == (f.get("before"), f.get("after"))
                for f in failures))


def gateway(cli, private, run):
    deadline = time.monotonic() + 90
    with (private / "gateway.log").open("wb") as log:
        p = subprocess.Popen(["node", cli, "gateway", "run", "--bind", "loopback", "--port", "18789"],
                             start_new_session=True, stdout=log, stderr=log)
        try:
            while time.monotonic() < deadline:
                if p.poll() is not None:
                    raise ValueError("GATEWAY_EARLY_EXIT")
                try:
                    with urlopen("http://127.0.0.1:18789/healthz", timeout=2) as response:
                        state = json.load(response)
                    if state.get("ok") is True and state.get("status") == "live":
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.5)
            else:
                raise ValueError("GATEWAY_LIVENESS_TIMEOUT")
            if run(["node", cli, "gateway", "health", "--json"], "health", max(1, deadline-time.monotonic())):
                raise ValueError("GATEWAY_RPC_FAILED")
            if json.loads((private / "health.log").read_text()).get("ok") is not True or p.poll() is not None:
                raise ValueError("GATEWAY_UNHEALTHY")
        finally:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
                    raise ValueError("GATEWAY_SHUTDOWN_TIMEOUT")
        if p.returncode not in (0, -signal.SIGTERM, 143):
            raise ValueError("GATEWAY_SHUTDOWN_FAILED")
