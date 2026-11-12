"""Run directly as a ZIP. All OpenClaw commands use the bundled fictional state."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

FILES = {"state/openclaw.sqlite", "agents/main/agent/openclaw-agent.sqlite",
         "workspace/IDENTITY.md", "workspace/USER.md"}
VERSIONS = {"2026.11.5-beta.1", "2026.11.5-beta.2"}


def installations():
    if len(sys.argv) > 1:
        yield Path(sys.argv[1])
        return
    for manifest in sorted(Path("/tmp").glob("orion-caller-*/staged.json"), reverse=True):
        try:
            if not manifest.is_file() or manifest.stat().st_size > 8_000_000:
                continue
            yield Path(json.loads(manifest.read_text())["sourcePackage"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    yield Path("/tmp/opencode/orion-discord-rehearsal-20261106/beta/pkg/package")
    executable = shutil.which("openclaw")
    if executable:
        yield Path(executable).resolve().parent
    yield Path("/usr/local/lib/node_modules/openclaw")
    yield Path("/usr/lib/node_modules/openclaw")


def find_package():
    for item in installations():
        try:
            p = item.resolve()
            if ".openclaw" in p.parts:
                continue
            package = json.loads((p / "package.json").read_text())
            if package.get("name") == "openclaw" and package.get("version") in VERSIONS and all(
                (p / f).is_file() for f in ("openclaw.mjs", "dist/plugin-sdk/session-transcript-runtime.js",
                                            "dist/plugin-sdk/session-store-runtime.js")
            ):
                return p, package["version"]
        except (OSError, ValueError, RuntimeError):
            continue
    raise ValueError("Could not find the staged beta.1 or beta.2 package. An explicit package directory can be passed after the ZIP name.")


def run():
    package, version = find_package()
    node = shutil.which("node")
    if not node:
        raise ValueError("Node is missing from PATH.")
    # These are the only inherited environment values. Use a new home, config, state and cache.
    env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "TZ", "LD_LIBRARY_PATH") if k in os.environ}
    with tempfile.TemporaryDirectory(prefix="orion-synthetic-phone-", dir="/tmp") as name:
        temp = Path(name)
        home, state = temp / "home", temp / "home" / ".openclaw"
        env.update(HOME=str(home), TMPDIR=str(temp / "tmp"), XDG_CONFIG_HOME=str(temp / "config"),
                   XDG_CACHE_HOME=str(temp / "cache"), XDG_DATA_HOME=str(temp / "data"),
                   XDG_STATE_HOME=str(temp / "xdg-state"), OPENCLAW_STATE_DIR=str(state),
                   OPENCLAW_CONFIG_PATH=str(state / "openclaw.json"), ORION_REHEARSAL_PACKAGE=str(package), CI="1")
        (temp / "tmp").mkdir()
        with zipfile.ZipFile(sys.argv[0]) as archive:
            hashes = json.loads(archive.read("hashes.json"))
            if set(hashes) != FILES:
                raise ValueError("Unexpected fixture manifest.")
            for label in sorted(FILES):
                info = archive.getinfo("fixture/" + label)
                if info.file_size > 64 * 1024 * 1024:
                    raise ValueError("Unexpected fixture size.")
                data = archive.read(info)
                if hashlib.sha256(data).hexdigest() != hashes[label]:
                    raise ValueError("Fixture checksum differs.")
                dest = state / label
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            for script in ("verify.mjs", "session.mjs"):
                (temp / script).write_bytes(archive.read(script))
        (state / "openclaw.json").write_text(json.dumps({"gateway":{"mode":"local"},"plugins":{"enabled":False}}))

        def call(*args, capture=False):
            result = subprocess.run([node, *args], cwd=temp, env=env, text=True, capture_output=True, timeout=100)
            if result.returncode:
                lines = (result.stderr or result.stdout).strip().splitlines()
                raise ValueError("Node exited "+str(result.returncode)+"\n"+"\n".join(lines[-10:]))
            if capture:
                return result.stdout
            print(result.stdout.strip(), flush=True)

        print("PACKAGE " + version, flush=True)
        call("-e", "const fs=require('node:fs');let s;try{fs.readlinkSync('/proc/self/ns/pid');s='visible'}catch(e){s=e.code}console.log('RUNTIME '+process.platform+'/'+process.arch+' '+process.version+' pid-link='+s)")
        call(str(temp / "verify.mjs"), "before")
        call(str(temp / "session.mjs"), "verify")
        listing = json.loads(call(str(package / "openclaw.mjs"), "sessions", "--agent", "main", "--json", capture=True))
        if not any(r.get("key") == "agent:main:main" and r.get("sessionId") == "5fd080f7-d376-483d-a065-c212db942f93"
                   for r in listing["sessions"]):
            raise ValueError("The CLI could not list the fictional session.")
        call(str(temp / "verify.mjs"), "after")
        if any(hashlib.sha256((state / p).read_bytes()).hexdigest() != hashes[p] for p in FILES if p.startswith("workspace/")):
            raise ValueError("The fictional workspace differs.")
    print("SYNTHETIC REHEARSAL PASS — 2 messages, 2 healthy databases, workspace verified.")


try:
    run()
except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
    print("SYNTHETIC REHEARSAL STOP — " + str(error), file=sys.stderr)
    sys.exit(1)
