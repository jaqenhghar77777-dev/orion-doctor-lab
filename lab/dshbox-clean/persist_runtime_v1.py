"""Copy the tested Orion runtime, switch v2 atomically, and check a normal chat."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

CHAT = Path("/root/orion-dshbox-chat-v1")
SOURCE = Path("/tmp/opencode/orion-discord-rehearsal-20261106/beta/pkg/package")
DURABLE = CHAT / "runtime-2026.11.5-beta.1"
LAUNCHER = CHAT / "orion_chat_v2.py"
BACKUP = DURABLE / "orion_chat_v2.before.py"
V2 = "2409f122b2b708ecdec1ece0b1ab825c361c1c645cf50dd02710ada0374164f9"
HELPER = "00551efe980d9ce71ab38a456ab90fc2c2aef841ddbf25f1436d73137e4adb4f"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def regular(path):
    require(path.resolve(strict=True) == path and path.is_file(), "unexpected file: " + path.name)
    return path.read_bytes()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").digest()


def updated(original, node, timeout):
    require(hashlib.sha256(original).hexdigest() == V2, "unexpected v2 launcher")
    changes = {
        'import CLI, HASHES': 'import HASHES',
        'CHAT = Path(': 'CLI = Path(' + repr(str(DURABLE / 'package/openclaw.mjs')) + ')\n\nCHAT = Path(',
        'node, timeout = shutil.which("node"), shutil.which("timeout")':
            'node, timeout = ' + repr(str(node)) + ', ' + repr(str(timeout)),
    }
    source = original.decode()
    for old, new in changes.items():
        require(source.count(old) == 1, "unexpected launcher layout")
        source = source.replace(old, new)
    compile(source, str(LAUNCHER), "exec")
    return source.encode()


def copy_package(source, dest):
    # npm may place node_modules beside the unpacked package or link to it.
    roots = [(source.resolve(strict=True), dest)]
    deps = next((p / "node_modules" for p in (source, *source.parents)
                 if (p / "node_modules").is_dir()), None)
    if deps:
        roots.insert(0, (deps.resolve(strict=True), dest / "node_modules"))
    seen = set()

    def mirror(src, dst):
        mode = src.lstat().st_mode
        if stat.S_ISLNK(mode):
            target = src.resolve(strict=True)
            for base, out in roots:
                if target.is_relative_to(base):
                    dst.symlink_to(os.path.relpath(out / target.relative_to(base), dst.parent))
                    return
            raise ValueError("external package link: " + src.name)
        if stat.S_ISDIR(mode):
            dst.mkdir(mode=0o700)
            for item in src.iterdir():
                if dst == dest and deps and item.name == "node_modules":
                    continue
                mirror(item, dst / item.name)
        elif stat.S_ISREG(mode):
            shutil.copyfile(src, dst)
            dst.chmod(0o700 if mode & 0o111 else 0o600)
            require(digest(src) == digest(dst), "copy mismatch: " + src.name)
            seen.add(dst)
        else:
            raise ValueError("special package entry: " + src.name)

    mirror(source.resolve(strict=True), dest)
    if deps:
        mirror(deps.resolve(strict=True), dest / "node_modules")
    for folder, dirs, files in os.walk(dest):
        for name in dirs + files:
            p = Path(folder) / name
            if p.is_symlink():
                require(p.resolve(strict=True).is_relative_to(dest), "link escaped copied runtime")
    return len(seen)


def main():
    os.umask(0o077)
    require(sys.stdin.isatty(), "interactive DSHBox terminal required")
    require(CHAT.resolve(strict=True) == CHAT, "unexpected chat path")
    require(hashlib.sha256(regular(CHAT / "openrouter_reply_v1.py")).hexdigest() == HELPER,
            "unexpected shared helper")
    programs = []
    for name in ("node", "timeout"):
        path = Path(shutil.which(name) or "").resolve(strict=True)
        require(path.is_file() and (path.is_relative_to("/usr") or path.is_relative_to("/root") or path.is_relative_to("/opt")), "inspect non-persistent " + name + " path")
        programs.append(path)
    node, timeout = programs
    require(subprocess.check_output([node, "-p", "process.platform+'/'+process.arch+' '+process.version"],
            env={"PATH":"/usr/local/bin:/usr/bin:/bin"}, text=True, timeout=15).strip()
            == "linux/arm64 v24.19.0", "unexpected Node runtime")
    sys.path.insert(0, str(CHAT))
    state = CHAT / "home/.openclaw"
    receipt_file = CHAT / "chat-session.json"
    with (CHAT / "chat.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        launcher = regular(LAUNCHER)
        original = regular(BACKUP) if DURABLE.exists() else launcher
        new = updated(original, node, timeout)
        require(launcher in (original, new), "unexpected installed launcher")
        import orion_chat_v2 as chat
        receipt = regular(receipt_file)
        saved = json.loads(receipt)
        session = str(uuid.UUID(saved["session_id"]))
        require(saved["config"] == json.loads(regular(state / "openclaw.json")), "saved config mismatch")
        chat.checked_workspace(state / "workspace")
        before = chat.events(state, session)
        require(any(e.get("message", {}).get("role") == "assistant" for e in before),
                "no prior assistant history under saved session ID")
        if not DURABLE.exists():
            with tempfile.TemporaryDirectory(dir=CHAT, prefix=".runtime-stage-") as tmp:
                stage = Path(tmp) / "runtime"
                stage.mkdir(mode=0o700)
                count = copy_package(SOURCE, stage / "package")
                (stage / BACKUP.name).write_bytes(original)
                stage.rename(DURABLE)
                print("Runtime files copied and hash-checked:", count, flush=True)
        cli = DURABLE / "package/openclaw.mjs"
        meta = json.loads((cli.parent / "package.json").read_text())
        require((meta["name"], meta["version"]) == ("openclaw", "2026.11.5-beta.1"), "package mismatch")
        with tempfile.TemporaryDirectory(dir=CHAT, prefix=".runtime-check-") as tmp:
            tmp = Path(tmp)
            env = chat.environment(tmp, tmp, tmp / "test-config.json")
            check = subprocess.run([timeout, "--kill-after=10s", "120", node, cli, "--version"],
                                   cwd=tmp, env=env, capture_output=True, text=True)
            require(check.returncode == 0 and meta["version"] in check.stdout, "copied CLI --version failed")
            if launcher != new:
                replacement = tmp / "launcher.py"
                replacement.write_bytes(new)
                replacement.chmod(0o700)
                os.replace(replacement, LAUNCHER)
    print("RUNTIME_READY — send one normal message with /send, then /quit after Orion replies.", flush=True)
    result = subprocess.run([sys.executable, "-B", LAUNCHER])
    require(result.returncode == 0, "chat exited unsuccessfully; check the launcher message")
    with (CHAT / "chat.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(regular(receipt_file) == receipt, "saved session receipt changed")
        chat.checked_workspace(state / "workspace")
        after = chat.events(state, session)
        require(after[:len(before)] == before, "previous transcript prefix differs")
        messages = [e.get("message", {}) for e in after[len(before):]]
        user_seen = False
        for message in messages:
            if message.get("role") == "user":
                user_seen = True
            if user_seen and message.get("role") == "assistant" and chat.text_content(message).strip():
                print("DURABLE_CHAT_PASS — prior history preserved, new reply in saved session, five files verified.")
                return
        raise ValueError("no new user turn followed by an assistant reply in the saved session")


if __name__ == "__main__":
    try:
        main()
    except BlockingIOError:
        sys.exit("DURABLE_CHAT_STOP — close the other Orion chat with /quit")
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        sys.exit("DURABLE_CHAT_STOP — " + str(error))
