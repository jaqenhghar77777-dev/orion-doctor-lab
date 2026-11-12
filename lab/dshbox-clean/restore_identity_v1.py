"""Restore four reviewed files to the stopped, successful DSHBox probe only."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

PROBE = Path("/root/orion-clean-gateway-op0iz8yu")
SOURCE = Path("/root/orion-export-review-BYY7Km/candidate/workspace")
HASHES = {
    "AGENTS.md": "490fc2b32865dd310a3af1225a409ac5c942d89ba456167feb0fd95e2807aaff",
    "SOUL.md": "9e8a5dbdfd6ab9938c521b29191293ad9039b3562e313d98bcc05174e4c3e6bf",
    "IDENTITY.md": "9ceb1b317c9b2f34ee3248db891a2cd285943511cad5f0cbc0898cff76cc52f2",
    "USER.md": "46e0d8c937df7b104de97a23c58537292672654194879ca9f76b02075e022555",
}


def regular(path):
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"unexpected file type or linked path: {path.name}")
    return path.read_bytes()


def restore(root, source, expected):
    receipt = json.loads(regular(root / "startup-report.json"))
    if (receipt.get("directory") != str(root) or receipt.get("result") != "PASS"
            or receipt.get("gateway_stopped") is not True):
        raise ValueError("successful stopped Gateway receipt required")
    workspace = root / "gateway/home/.openclaw/workspace"
    if workspace.parent.resolve(strict=True) != workspace.parent or workspace.resolve() != workspace:
        raise ValueError("unexpected workspace path")
    data = {name: regular(source / name) for name in expected}
    def verify(content, name):
        if hashlib.sha256(content).hexdigest() != expected[name]:
            raise ValueError(f"hash mismatch: {name}")
    for name in expected:
        verify(data[name], name)

    prior = {}
    for name in expected:
        target = workspace / name
        if target.is_symlink() or target.exists():
            prior[name] = regular(target)
    changed = [name for name in expected if prior.get(name) != data[name]]
    if changed:
        stash = Path(tempfile.mkdtemp(prefix="identity-restore-", dir=root))
        backup = stash / "previous"
        backup.mkdir()
        (stash / "previously-absent.json").write_text(json.dumps([n for n in changed if n not in prior]))
        for name in changed:
            if name in prior:
                (backup / name).write_bytes(prior[name])
            (stash / name).write_bytes(data[name])
        print("Private rollback directory", stash, flush=True)
        workspace.mkdir(mode=0o700, exist_ok=True)
        installed = []
        try:
            for name in changed:
                os.replace(stash / name, workspace / name)
                installed.append(name)
            for name in expected:
                verify(regular(workspace / name), name)
        except BaseException:
            for name in reversed(installed):
                if name in prior:
                    os.replace(backup / name, workspace / name)
                else:
                    (workspace / name).unlink()
            raise
    for name in expected:
        verify(regular(workspace / name), name)
        print(name, "OK")
    print("IDENTITY_PASS", workspace)


if __name__ == "__main__":
    os.umask(0o077)
    try:
        restore(PROBE, SOURCE, HASHES)
    except (OSError, ValueError, TypeError) as error:
        print("IDENTITY_STOP", str(error), file=sys.stderr)
        sys.exit(1)
