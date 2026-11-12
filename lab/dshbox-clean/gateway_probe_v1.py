"""One phone-local, offline-configured Gateway startup probe."""
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

PACKAGE = Path("/tmp/opencode/orion-discord-rehearsal-20261106/beta/pkg/package")
VERSION = "2026.11.5-beta.1"
STARTUP_SECONDS = 90


def environment(base):
    home = base / "home"
    state = home / ".openclaw"
    state.mkdir(parents=True, mode=0o700)
    env = {"PATH": os.environ.get("PATH", os.defpath), "LANG": "C.UTF-8", "HOME": str(home),
           "OPENCLAW_HOME": str(home), "OPENCLAW_STATE_DIR": str(state),
           "OPENCLAW_CONFIG_PATH": str(state / "openclaw.json"), "OPENCLAW_SKIP_CHANNELS": "1",
           "OPENCLAW_DISABLE_BONJOUR": "1", "NODE_DISABLE_COMPILE_CACHE": "1",
           "NO_COLOR": "1", "CI": "1"}
    for name in ("TMPDIR", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
        directory = base / name.lower()
        directory.mkdir(mode=0o700)
        env[name] = str(directory)
    return env


def stop_group(proc):
    # Only signal the new session created by this script.
    for sig, wait in ((signal.SIGTERM, 5), (signal.SIGKILL, 2)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            break
        end = time.monotonic() + wait
        while time.monotonic() < end:
            proc.poll()
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
    proc.wait(timeout=2)
    try:
        os.killpg(proc.pid, 0)
    except ProcessLookupError:
        return
    raise RuntimeError("probe process group still present after cleanup")


def diagnostic(raw, token, root):
    text = raw.replace(token, "[redacted]").replace(str(root), "<probe>")
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|\Z)', '[redacted key]', text, flags=re.S)
    text = re.sub(r'(?i)\bBearer\s+\S+|(?:gh[pousr]_|github_pat_|sk-)[\w-]{8,}', '[redacted]', text)
    text = re.sub(r'(?i)(["\']?(?:token|password|secret|api[_-]?key|authorization)["\']?\s*[:=]\s*)("[^"]*"|\S+)', r'\1[redacted]', text)
    lines = [''.join(c for c in line if c.isprintable())[:360] for line in text.splitlines() if line.strip()]
    errors = [line for line in lines if re.search(r'error|fail|refus|denied|missing|cannot|invalid|lock|requires|blocked|not found', line, re.I)]
    return list(dict.fromkeys(errors[:4] + lines[-5:]))


def health(port):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        conn.request("GET", "/healthz")
        res = conn.getresponse()
        body = res.read(4097)
        if res.status != 200 or len(body) > 4096:
            return False
        data = json.loads(body)
        return isinstance(data, dict) and data.get("ok") is True and data.get("status") == "live"
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        conn.close()


def probe(root, package):
    token = secrets.token_urlsafe(32)
    report = {"result": "STOP", "stage": "runtime", "directory": str(root)}
    raw = ""
    try:
        meta = json.loads((package / "package.json").read_text())
        if (meta["name"], meta["version"], meta["bin"]["openclaw"]) != ("openclaw", VERSION, "openclaw.mjs"):
            raise RuntimeError("staged OpenClaw package differs from the previously tested beta.1")
        node = shutil.which("node")
        if not node:
            raise RuntimeError("node unavailable")
        node = str(Path(node).resolve(strict=True))
        cli = str((package / "openclaw.mjs").resolve(strict=True))
        verify = environment(root / "preflight")

        def check(args, stage):
            nonlocal raw
            report["stage"] = stage
            raw = ""
            with tempfile.TemporaryFile(dir=root) as output, tempfile.TemporaryFile(dir=root) as errors:
                p = subprocess.Popen([node, *args], env=verify, cwd=verify["HOME"], start_new_session=True,
                                     stdin=subprocess.DEVNULL, stdout=output, stderr=errors)
                try:
                    rc = p.wait(timeout=45)
                finally:
                    stop_group(p)
                    for stream in (output, errors):
                        stream.seek(max(0, stream.seek(0, 2)-16384))
                        raw += stream.read().decode(errors="replace") + "\n"
                if rc:
                    raise RuntimeError(f"{stage} exited {rc}")
                output.seek(0)
                return output.read(256000).decode(errors="replace").strip()

        runtime = check(["-p", "process.platform+'/'+process.arch+' '+process.version"], "node runtime")
        if not re.fullmatch(r"linux/arm64 v\d+\.\d+\.\d+", runtime):
            raise RuntimeError("expected linux/arm64 Node")
        report["node"] = runtime
        version = check([cli, "--version"], "OpenClaw version")
        if not re.search(r"(?<![\w.-])" + re.escape(VERSION) + r"(?![\w.-])", version):
            raise RuntimeError("CLI version differs from package manifest")
        report["openclaw"] = VERSION
        help_text = check([cli, "gateway", "run", "--help"], "gateway CLI")
        if not all(flag in help_text for flag in ("--bind", "--port")):
            raise RuntimeError("gateway run lacks a requested flag")

        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
            config = json.dumps({"gateway": {"mode":"local","bind":"loopback","port":port,
                                             "auth":{"mode":"token","token":token}},
                                 "channels": {}, "plugins": {"enabled":False},
                                 "logging":{"file":str(root / "openclaw.log")}})
            cfg = Path(verify["OPENCLAW_CONFIG_PATH"])
            cfg.write_text(config)
            result = json.loads(check([cli, "config", "validate", "--json"], "config validation"))
            if result.get("valid") is not True or result.get("path") != str(cfg):
                raise RuntimeError("validator did not confirm the isolated configuration path")
            report["config_valid"] = True
            live = environment(root / "gateway")
            state = Path(live["OPENCLAW_STATE_DIR"])
            if any(state.iterdir()):
                raise RuntimeError("startup state is not empty")
            Path(live["OPENCLAW_CONFIG_PATH"]).write_text(config)
        report["stage"], raw = "gateway startup", ""
        print("PREFLIGHT_PASS", runtime, VERSION, "isolated config accepted; starting Gateway", flush=True)
        with tempfile.TemporaryFile(dir=root) as log:
            proc = subprocess.Popen([node, cli, "gateway", "run", "--bind", "loopback", "--port", str(port)],
                                    cwd=live["HOME"], env=live, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                deadline = time.monotonic() + STARTUP_SECONDS
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        raise RuntimeError(f"gateway exited {proc.returncode} before live health response")
                    if health(port) and proc.poll() is None:
                        break
                    time.sleep(0.4)
                else:
                    raise RuntimeError(f"no live HTTP 200 from /healthz within {STARTUP_SECONDS} seconds")
            finally:
                stop_group(proc)
                log.seek(max(0, log.seek(0, 2)-32768))
                raw = log.read().decode(errors="replace")
        if health(port):
            raise RuntimeError("health endpoint still live after stopping test process")
        report.update(result="PASS", stage="complete", health="HTTP 200, ok=true, status=live", gateway_stopped=True)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        if report["stage"] == "gateway startup":
            app_log = root / "openclaw.log"
            if app_log.is_file():
                with app_log.open("rb") as f:
                    f.seek(max(0, f.seek(0, 2)-8192))
                    raw += "\n" + f.read().decode(errors="replace")
        report["reason"] = diagnostic(str(error), token, root)
        report["diagnostic"] = diagnostic(raw, token, root)
    return report


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise RuntimeError("phone probe interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    os.umask(0o077)
    root = Path(tempfile.mkdtemp(prefix="orion-clean-gateway-", dir="/root"))
    result = probe(root, PACKAGE)
    receipt = json.dumps(result, indent=2)
    (root / "startup-report.json").write_text(receipt+"\n")
    print(receipt)
    sys.exit(0 if result["result"] == "PASS" else 1)
