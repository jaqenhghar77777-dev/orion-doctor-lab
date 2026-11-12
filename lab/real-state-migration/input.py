"""Validate the exact reviewed archive before extracting regular payload files."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile

ARCHIVE_SHA = "d991442d8e5175dd2d38eb7402c148507b93d855a5e91d4ffe6038c059bfffd3"
MANIFEST_SHA = "38cc930e6aa93cb14b0eb6f7f0e4b9babf51ab1bf95ceef34cd70d554e7864ad"
NAMES = {"agents/main/agent/openclaw-agent.sqlite",
         "agents/openclaw/agent/openclaw-agent.sqlite", "state/openclaw.sqlite",
         "workspace/AGENTS.md", "workspace/SOUL.md", "workspace/IDENTITY.md", "workspace/USER.md"}


def extract(archive, destination):
    if archive.stat().st_size != 2744028:
        raise ValueError("INPUT_ARCHIVE_SIZE_MISMATCH")
    raw = archive.read_bytes()
    if len(raw) != 2744028 or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA:
        raise ValueError("INPUT_ARCHIVE_MISMATCH")
    destination.mkdir(mode=0o755)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if len(names) != 8 or set(names) != NAMES | {"manifest.json"}:
            raise ValueError("INPUT_MEMBER_SET_MISMATCH")
        if any(not m.isfile() or m.size > 64 * 1024 * 1024 for m in members):
            raise ValueError("INPUT_MEMBER_TYPE_OR_SIZE")
        manifest_data = tar.extractfile("manifest.json").read()
        if hashlib.sha256(manifest_data).hexdigest() != MANIFEST_SHA:
            raise ValueError("INPUT_MANIFEST_MISMATCH")
        manifest = json.loads(manifest_data)
        indexed = {i["path"]: i for i in manifest["files"]}
        if len(manifest["files"]) != 7 or set(indexed) != NAMES:
            raise ValueError("INPUT_PAYLOAD_SET_MISMATCH")
        for item in members:
            data = tar.extractfile(item).read()
            if item.name != "manifest.json":
                expected = indexed[item.name]
                if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                    raise ValueError("INPUT_PAYLOAD_HASH_MISMATCH")
            output = destination / item.name
            output.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            with output.open("xb") as f:
                f.write(data)
            output.chmod(0o444)
    print("INPUT_PASS reviewed archive and eight regular members verified")


if __name__ == "__main__":
    try:
        extract(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, KeyError, tarfile.TarError, EOFError):
        print("INPUT_STOP archive validation failed")
        raise SystemExit(1)
