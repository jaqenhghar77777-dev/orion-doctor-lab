"""Provision a private home for stock OpenClaw. No Gateway or chat is started here."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile

CHAT = Path("/root/orion-dshbox-chat-v1")
ROOT = Path("/root/orion-full-gateway-v1")
VERSION = "2026.11.5-beta.1"
PACKAGE = CHAT / ("runtime-" + VERSION) / "package"
NOTE = "memory/orion-recovery/orion-recovered-v1.md"
FILES = {
    "SOUL.md": "9e8a5dbdfd6ab9938c521b29191293ad9039b3562e313d98bcc05174e4c3e6bf",
    "IDENTITY.md": "9ceb1b317c9b2f34ee3248db891a2cd285943511cad5f0cbc0898cff76cc52f2",
    "AGENTS.md": "490fc2b32865dd310a3af1225a409ac5c942d89ba456167feb0fd95e2807aaff",
    "USER.md": "46e0d8c937df7b104de97a23c58537292672654194879ca9f76b02075e022555",
    NOTE: "70d188735194c06ad540385491f902fa6079b2393aac8b3ca0dc74af5fdc3606",
}


def layout(base):
    home = base / "home"
    state = home / ".openclaw"
    return {"HOME": home, "OPENCLAW_HOME": home, "OPENCLAW_STATE_DIR": state,
            "OPENCLAW_CONFIG_PATH": state / "openclaw.json",
            "OPENCLAW_WORKSPACE_DIR": state / "workspace",
            **{k: base / k.lower() for k in ("TMPDIR", "XDG_CONFIG_HOME", "XDG_STATE_HOME",
               "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}}


def initialize(base):
    paths = layout(base)
    for k, p in paths.items():
        if k != "OPENCLAW_CONFIG_PATH":
            p.mkdir(parents=True, mode=0o700, exist_ok=True)
    return paths


def main():
    os.umask(0o077)
    if os.path.lexists(ROOT):
        sys.exit("SETUP_STOP — destination already exists; use the existing setup or inspect it first")
    cli = PACKAGE / "openclaw.mjs"
    if cli.resolve(strict=True) != cli:
        raise ValueError("unexpected linked CLI")
    meta = json.loads((PACKAGE / "package.json").read_bytes())
    if (meta["name"], meta["version"]) != ("openclaw", VERSION):
        raise ValueError("unexpected persistent runtime")
    node = Path(shutil.which("node") or "").resolve(strict=True)
    path = os.pathsep.join(dict.fromkeys([str(node.parent), "/usr/local/bin", "/usr/bin", "/bin"]))
    common = {"PATH": path, "LANG": "C.UTF-8", "OPENCLAW_SKIP_CHANNELS": "1",
              "OPENCLAW_DISABLE_BONJOUR": "1", "NODE_DISABLE_COMPILE_CACHE": "1"}
    with tempfile.TemporaryDirectory(prefix=".orion-gateway-setup-", dir=ROOT.parent) as tmp:
        stage = Path(tmp) / "ready"
        dst = initialize(stage)
        probe = initialize(Path(tmp) / "preflight")
        env = {**common, **{k: str(v) for k, v in probe.items()}}
        def check(args):
            p = subprocess.run(["/usr/bin/timeout", "--kill-after=10s", "120", node, *args],
                               cwd=probe["HOME"], env=env, capture_output=True, text=True)
            if p.returncode:
                raise ValueError("preflight failed at " + " ".join(map(str,args[1:])) + " exit " + str(p.returncode))
            return p.stdout
        if check(["-p", "process.platform+'/'+process.arch+' '+process.version"]).strip() != "linux/arm64 v24.19.0":
            raise ValueError("unexpected Node runtime")
        if VERSION not in check([cli, "--version"]):
            raise ValueError("CLI version mismatch")
        for cmd, flag in [(["gateway","run"],"--bind"), (["tui"],"--session"), (["dashboard"],"--no-open")]:
            if flag not in check([cli,*cmd,"--help"]):
                raise ValueError("installed CLI lacks " + " ".join(cmd+[flag]))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        final = layout(ROOT)
        config = {"gateway":{"mode":"local","bind":"loopback","port":port,
                             "auth":{"mode":"token","token":secrets.token_urlsafe(32)},
                             "controlUi":{"enabled":True}},
                  "channels":{}, "plugins":{"enabled":True,"allow":["openrouter"]},
                  "agents":{"defaults":{"workspace":str(final["OPENCLAW_WORKSPACE_DIR"]),
                                        "model":{"primary":"openrouter/openrouter/free","fallbacks":[]}}},
                  "tools":{"allow":["read"],"fs":{"workspaceOnly":True}},
                  "logging":{"file":str(ROOT / "gateway.log")}}
        data = json.dumps(config,indent=2)
        probe["OPENCLAW_CONFIG_PATH"].write_text(data)
        result = json.loads(check([cli,"config","validate","--json"]))
        if result.get("valid") is not True or result.get("path") != str(probe["OPENCLAW_CONFIG_PATH"]):
            raise ValueError("validator did not confirm isolated config")
        dst["OPENCLAW_CONFIG_PATH"].write_text(data)
        for name, expected in FILES.items():
            src = CHAT / "home/.openclaw/workspace" / name
            if src.resolve(strict=True) != src or not src.is_file():
                raise ValueError("unexpected source for " + name)
            out = dst["OPENCLAW_WORKSPACE_DIR"] / name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src,out)
            if hashlib.sha256(out.read_bytes()).hexdigest() != expected:
                raise ValueError("document hash mismatch: " + name)
        (dst["OPENCLAW_WORKSPACE_DIR"] / "MEMORY.md").write_text(
            "# Orion's recovered knowledge\n\nRead USER.md for the original profile document. "
            "Read " + NOTE + " for recovered historical knowledge.\n")
        binary = stage / "bin/openclaw"
        binary.parent.mkdir()
        settings = " ".join(shlex.quote(k+"="+str(v)) for k,v in {**common,**final}.items())
        # The stock CLI owns the terminal. Ask for a key only for the foreground
        # Gateway and keep it in the process environment for this run.
        entry = stage / "bin/entry"
        entry.write_text("""#!/bin/bash
set -eu
if [[ ${1:-} == gateway && ${2:-} == run ]]; then
    read -rsp 'OpenRouter key (hidden; Enter for interface-only test): ' OPENROUTER_API_KEY
    printf '\\n'
    export OPENROUTER_API_KEY
fi
exec """ + shlex.quote(str(node)) + " " + shlex.quote(str(cli)) + ' "$@"\n')
        entry.chmod(0o700)
        binary.write_text("#!/bin/sh\nset -eu\numask 077\ncd " +
                          shlex.quote(str(final["OPENCLAW_WORKSPACE_DIR"])) +
                          '\nexec /usr/bin/env -i -- ' + settings +
                          ' TERM="${TERM:-xterm-256color}" ' +
                          shlex.quote(str(ROOT / "bin/entry")) + ' "$@"\n')
        binary.chmod(0o700)
        if ROOT.exists():
            raise ValueError("destination appeared during setup")
        stage.rename(ROOT)
        print("SETUP_PASS — beta.1 CLI, isolated config and five document hashes verified")
        print("Health URL: http://127.0.0.1:" + str(port) + "/healthz")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        sys.exit("SETUP_STOP — " + str(error))
