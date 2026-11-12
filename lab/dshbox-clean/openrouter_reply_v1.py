"""One local OpenClaw agent turn with an ephemeral OpenRouter credential."""
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path("/root/orion-clean-gateway-op0iz8yu")
CLI = Path("/tmp/opencode/orion-discord-rehearsal-20261106/beta/pkg/package/openclaw.mjs")
MODEL = "openrouter/openrouter/free"
NOTE = "memory/orion-recovery/orion-recovered-v1.md"
HASHES = {
    "SOUL.md": "9e8a5dbdfd6ab9938c521b29191293ad9039b3562e313d98bcc05174e4c3e6bf",
    "IDENTITY.md": "9ceb1b317c9b2f34ee3248db891a2cd285943511cad5f0cbc0898cff76cc52f2",
    "AGENTS.md": "490fc2b32865dd310a3af1225a409ac5c942d89ba456167feb0fd95e2807aaff",
    "USER.md": "46e0d8c937df7b104de97a23c58537292672654194879ca9f76b02075e022555",
    NOTE: "70d188735194c06ad540385491f902fa6079b2393aac8b3ca0dc74af5fdc3606",
}


def checked_workspace(workspace):
    for name, expected in HASHES.items():
        file = workspace / name
        if file.resolve(strict=True) != file or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError("workspace verification failed: " + name)


def result_text(data):
    if not isinstance(data, dict):
        raise ValueError("unexpected response format")
    for response in [data, data.get("result")]:
        if not isinstance(response, dict):
            continue
        meta = response.get("meta") or {}
        if response.get("error") or meta.get("error") or meta.get("aborted") or data.get("ok") is False:
            raise ValueError("agent reported a failed turn")
        payloads = response.get("payloads") or []
        if any(p.get("isError") for p in payloads):
            raise ValueError("agent returned a provider or runtime error")
        texts = [p["text"] for p in payloads if isinstance(p.get("text"), str) and p["text"].strip()]
        if texts:
            return "\n".join(texts)
    raise ValueError("no assistant text in the reply")


def main():
    os.umask(0o077)
    base = ROOT / "gateway"
    home = base / "home"
    state = home / ".openclaw"
    workspace = state / "workspace"
    checked_workspace(workspace)
    package = json.loads((CLI.parent / "package.json").read_text())
    if package["name"] != "openclaw" or package["version"] != "2026.11.5-beta.1":
        raise ValueError("unexpected OpenClaw package")
    node = shutil.which("node")
    if not node or not sys.stdin.isatty():
        raise ValueError("run from an interactive DSHBox terminal with Node installed")
    # A separate configuration selects a provider for this turn only.
    with tempfile.TemporaryDirectory(prefix="reply-", dir=ROOT) as tmp:
        config = Path(tmp) / "openclaw.json"
        original = json.loads((state / "openclaw.json").read_text())
        config.write_text(json.dumps({
            "gateway":original["gateway"], "channels":{},
            "plugins":{"enabled":True,"allow":["openrouter"]},
            "agents":{"defaults":{"workspace":str(workspace),"model":{"primary":MODEL,"fallbacks":[]}}},
            "tools":{"allow":["read"],"fs":{"workspaceOnly":True}},
            "logging":{"file":str(Path(tmp) / "app.log")},
        }))
        env = {"PATH":os.environ["PATH"],"LANG":"C.UTF-8","HOME":str(home),"OPENCLAW_HOME":str(home),
               "OPENCLAW_STATE_DIR":str(state),"OPENCLAW_CONFIG_PATH":str(config),
               "OPENCLAW_SKIP_CHANNELS":"1","OPENCLAW_DISABLE_BONJOUR":"1","NO_COLOR":"1",
               "CI":"1","NODE_DISABLE_COMPILE_CACHE":"1"}
        for k in ("TMPDIR","XDG_CONFIG_HOME","XDG_STATE_HOME","XDG_DATA_HOME","XDG_CACHE_HOME","XDG_RUNTIME_DIR"):
            env[k] = str(base / k.lower())
        timeout = shutil.which("timeout")
        if not timeout:
            raise ValueError("GNU timeout unavailable")
        def call(seconds, *args):
            return subprocess.run([timeout, "--kill-after=10s", str(seconds), node, str(CLI), *args],
                                  cwd=home,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True)
        check = call(120, "config","validate","--json")
        if check.returncode:
            raise ValueError("temporary OpenRouter configuration validation failed (exit %d)" % check.returncode)
        parsed = json.loads(check.stdout)
        if parsed.get("valid") is not True or parsed.get("path") != str(config):
            raise ValueError("unexpected validation receipt")
        key = getpass.getpass("OpenRouter API key (hidden): ").strip()
        if not key:
            raise ValueError("empty key")
        env["OPENROUTER_API_KEY"] = key
        prompt = ("Greet me in your usual voice using your workspace identity. Use the read tool to read "
                  "only the first 24 lines of " + NOTE + ". Mention one harmless detail you recognize. "
                  "Finish with a line beginning 'Memory: ' followed by a short exact phrase from the body "
                  "of an excerpt. Skip names of third parties, credentials and contact details. "
                  "If the note is inaccessible, say so. Keep the reply under 80 words.")
        print("Calling Orion once. Allow up to six minutes.", flush=True)
        run = call(360, "agent","--local","--agent","main","--model",MODEL,"--timeout","180",
                   "--message",prompt,"--json")
        checked_workspace(workspace)
        try:
            if run.returncode:
                raise ValueError("CLI exit %d" % run.returncode)
            reply = result_text(json.loads(run.stdout))
        except (ValueError, TypeError) as error:
            # Classify errors without exposing provider bodies, prompts, credentials or notes.
            raw = run.stdout + "\n" + run.stderr
            patterns = [("KEY_REJECTED",r"\b401\b|invalid api key|no auth credentials|no api key"),
                        ("RATE_LIMIT",r"\b429\b|rate.limit"),("ACCESS_DENIED",r"\b403\b"),
                        ("NO_MODEL_ROUTE",r"no endpoints|unknown model|model not found"),
                        ("OWNERSHIP_REFUSAL",r"offline maintenance|state lease|already running"),
                        ("PROVIDER_UNAVAILABLE",r"\b503\b|provider unavailable")]
            label = next((tag for tag, pattern in patterns if re.search(pattern,raw,re.I)), "TURN_FAILED")
            if run.returncode in (124,137): label = "TIMEOUT"
            raise ValueError(f"{label} (exit {run.returncode})") from error
        reply = reply.replace(key,"[redacted]")
        print("\n" + reply)
        match = re.search(r"^Memory:\s*(.+)$",reply,re.I|re.M)
        quote = match[1].strip().strip('"“”') if match else ""
        bodies = re.split(r"\n## Excerpt \d+\n\nSource [^\n]*\n\n",(workspace / NOTE).read_text())[1:]
        matched = len(quote) >= 12 and any(quote in body for body in bodies)
        print("\nOPENROUTER_REPLY_RECEIVED", "MEMORY_QUOTE_MATCH" if matched else "MEMORY_UNCONFIRMED")


if __name__ == "__main__":
    try:
        main()
    except (ValueError,OSError,KeyError,EOFError) as error:
        print("OPENROUTER_STOP", error, file=sys.stderr)
        sys.exit(1)
