"""Persistent phone-local chat using Orion's verified recovery documents."""
import fcntl
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid

from openrouter_reply_v1 import CLI, HASHES, ROOT, MODEL, checked_workspace, result_text, validator_issues

CHAT = Path("/root/orion-dshbox-chat-v1")


def initialize():
    if os.path.lexists(CHAT):
        if CHAT.resolve(strict=True) != CHAT:
            raise ValueError("chat directory is linked")
        return
    source = ROOT / "gateway/home/.openclaw/workspace"
    checked_workspace(source)
    # This is independent OpenClaw state, populated only with the five verified documents.
    with tempfile.TemporaryDirectory(prefix="orion-chat-setup-", dir=CHAT.parent) as tmp:
        stage = Path(tmp) / "ready"
        home = stage / "home"
        workspace = home / ".openclaw/workspace"
        for name in HASHES:
            file = workspace / name
            file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(source / name, file)
        checked_workspace(workspace)
        state = CHAT / "home/.openclaw"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        config = {
            "gateway":{"mode":"local","bind":"loopback","port":port,
                       "auth":{"mode":"token","token":secrets.token_urlsafe(32)}},
            "channels":{}, "plugins":{"enabled":True,"allow":["openrouter"]},
            "agents":{"defaults":{"workspace":str(state / "workspace"),
                                  "model":{"primary":MODEL,"fallbacks":[]}}},
            "tools":{"allow":["read"],"fs":{"workspaceOnly":True}},
            "logging":{"file":str(CHAT / "app.log")},
        }
        (workspace.parent / "openclaw.json").write_text(json.dumps(config))
        (stage / "chat-session.json").write_text(json.dumps({
            "format":"orion-dshbox-chat-v1","session_id":str(uuid.uuid4()),"config":config}))
        for name in ("orion_chat_v1.py","openrouter_reply_v1.py"):
            shutil.copyfile(Path(__file__).parent / name, stage / name)
        stage.rename(CHAT)


def main():
    os.umask(0o077)
    if not sys.stdin.isatty():
        raise ValueError("run from an interactive DSHBox terminal")
    meta = json.loads((CLI.parent / "package.json").read_text())
    if meta["name"] != "openclaw" or meta["version"] != "2026.11.5-beta.1":
        raise ValueError("unexpected OpenClaw installation")
    node, timeout = shutil.which("node"), shutil.which("timeout")
    if not node or not timeout:
        raise ValueError("Node and GNU timeout are required")
    initialize()
    with (CHAT / "chat.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("this chat launcher is already running")
        home = CHAT / "home"
        state = home / ".openclaw"
        workspace = state / "workspace"
        checked_workspace(workspace)
        receipt = json.loads((CHAT / "chat-session.json").read_text())
        if receipt.get("format") != "orion-dshbox-chat-v1":
            raise ValueError("unexpected chat state")
        session = receipt["session_id"]
        if str(uuid.UUID(session)) != session:
            raise ValueError("unexpected chat session")
        config = state / "openclaw.json"
        if config.resolve(strict=True) != config or json.loads(config.read_text()) != receipt["config"]:
            raise ValueError("chat config differs from the saved setup")
        env = {"PATH":os.environ["PATH"],"LANG":"C.UTF-8","HOME":str(home),"OPENCLAW_HOME":str(home),
               "OPENCLAW_STATE_DIR":str(state),"OPENCLAW_CONFIG_PATH":str(config),
               "OPENCLAW_SKIP_CHANNELS":"1","OPENCLAW_DISABLE_BONJOUR":"1",
               "NODE_DISABLE_COMPILE_CACHE":"1","NO_COLOR":"1","CI":"1"}
        for name in ("TMPDIR","XDG_CONFIG_HOME","XDG_STATE_HOME","XDG_DATA_HOME","XDG_CACHE_HOME","XDG_RUNTIME_DIR"):
            folder = CHAT / name.lower()
            if folder.resolve() != folder:
                raise ValueError("linked chat runtime directory")
            folder.mkdir(mode=0o700, exist_ok=True)
            env[name] = str(folder)
        def call(seconds, *args):
            return subprocess.run([timeout,"--kill-after=10s",str(seconds),node,str(CLI),*args],
                                  env=env,cwd=home,stdin=subprocess.DEVNULL,capture_output=True,text=True)
        valid = call(120,"config","validate","--json")
        if valid.returncode:
            issues = validator_issues(valid,receipt["config"]["gateway"])
            print(json.dumps({"result":"CHAT_CONFIG_STOP","issues":issues},indent=2))
            return 1
        validation = json.loads(valid.stdout)
        if validation.get("valid") is not True or validation.get("path") != str(config):
            raise ValueError("unexpected config validation result")
        key = getpass.getpass("OpenRouter API key (hidden): ").strip()
        if not key:
            raise ValueError("empty key")
        env["OPENROUTER_API_KEY"] = key
        print("CHAT_READY — conversation saved on this phone. Type /quit to leave.",flush=True)
        while True:
            try:
                prompt = input("\nYou: ").strip()
            except EOFError:
                break
            if prompt == "/quit":
                break
            if not prompt:
                continue
            print("Orion is thinking...",flush=True)
            run = call(360,"agent","--local","--agent","main","--session-id",session,
                       "--model",MODEL,"--timeout","180","--message",prompt,"--json")
            checked_workspace(workspace)
            if run.returncode:
                raw = run.stdout + "\n" + run.stderr
                patterns = [("OWNERSHIP_REFUSAL",r"GatewayLockNamespaceError|cannot verify Gateway ownership|offline maintenance|state lease|already running"),
                            ("KEY_REJECTED",r"\b401\b|invalid api key|no api key|no auth credentials"),
                            ("RATE_LIMIT",r"\b429\b|rate.limit"),("MODEL_UNAVAILABLE",r"no endpoints|unknown model|\b503\b")]
                code = next((name for name,pattern in patterns if re.search(pattern,raw,re.I)),"TURN_FAILED")
                if run.returncode in (124,137): code="TIMEOUT"
                raise ValueError(f"{code}, exit {run.returncode}. Chat state retained; the turn was not retried.")
            reply = result_text(json.loads(run.stdout)).replace(key,"[redacted]")
            print("\nOrion: "+reply,flush=True)
        print("CHAT_CLOSED — saved conversation retained.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCHAT_STOP — interrupted; conversation state retained.")
        sys.exit(130)
    except (OSError,ValueError,KeyError,EOFError) as error:
        print("CHAT_STOP",str(error),file=sys.stderr)
        sys.exit(1)
