"""Recover reviewed memory text into one private note in the verified DSHBox workspace."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path("/root/orion-clean-gateway-op0iz8yu")
ARCHIVE = Path("/root/orion-export-review-BYY7Km/orion_sanitized_rehearsal_v1.tar.gz")
ARCHIVE_HASH = "d991442d8e5175dd2d38eb7402c148507b93d855a5e91d4ffe6038c059bfffd3"
MANIFEST_HASH = "38cc930e6aa93cb14b0eb6f7f0e4b9babf51ab1bf95ceef34cd70d554e7864ad"
MAIN = "agents/main/agent/openclaw-agent.sqlite"
IDENTITY = ("AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md")

READ_CHUNKS = """
const { DatabaseSync } = require('node:sqlite');
const db = new DatabaseSync(process.argv[1], {readOnly:true});
try {
  db.exec('PRAGMA query_only=ON');
  const rows = db.prepare(`SELECT path, start_line, end_line, CAST(text AS BLOB) AS bytes
    FROM memory_index_chunks ORDER BY path, start_line, end_line, id, chunk_rowid`).all();
  process.stdout.write(JSON.stringify(rows.map(r => [r.path, r.start_line, r.end_line,
    Buffer.from(r.bytes).toString('base64')])));
} finally { db.close(); }
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("expected a regular file in its original directory")
    return path.read_bytes()


def recover(root, archive, archive_hash, manifest_hash):
    receipt = json.loads(regular(root / "startup-report.json"))
    if (receipt.get("result"), receipt.get("gateway_stopped"), receipt.get("directory")) != ("PASS", True, str(root)):
        raise ValueError("stopped Gateway PASS receipt required")
    workspace = root / "gateway/home/.openclaw/workspace"
    if workspace.resolve(strict=True) != workspace:
        raise ValueError("workspace path mismatch")
    raw = regular(archive)
    if sha(raw) != archive_hash:
        raise ValueError("reviewed archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        def member(name):
            entry = tar.getmember(name)
            if not entry.isfile():
                raise ValueError("expected a regular archive member")
            return tar.extractfile(entry).read()
        manifest = member("manifest.json")
        if sha(manifest) != manifest_hash:
            raise ValueError("reviewed manifest checksum mismatch")
        files = {i["path"]: i["sha256"] for i in json.loads(manifest)["files"]}
        db = member(MAIN)
    if sha(db) != files[MAIN]:
        raise ValueError("source database checksum mismatch")

    def check_identity():
        for name in IDENTITY:
            if sha(regular(workspace / name)) != files["workspace/" + name]:
                raise ValueError("identity checksum mismatch: " + name)
    check_identity()
    with tempfile.TemporaryDirectory(prefix=".notes-", dir=root) as directory:
        temp = Path(directory)
        copy = temp / "source.sqlite"
        copy.write_bytes(db)
        node = shutil.which("node")
        if not node:
            raise ValueError("Node runtime unavailable")
        read = subprocess.run([node, "--no-warnings", "--input-type=commonjs", "-e", READ_CHUNKS, str(copy)],
                              cwd=temp, env={"PATH": os.environ.get("PATH", os.defpath), "HOME":directory,
                                             "TMPDIR":directory, "NODE_DISABLE_COMPILE_CACHE":"1"},
                              capture_output=True, timeout=60)
        if read.returncode:
            raise ValueError("read-only SQLite extraction failed (exit " + str(read.returncode) + ")")
        rows = json.loads(read.stdout)
        if len(rows) != 70:
            raise ValueError("expected 70 reviewed chunks")
        content = bytearray(b"# Orion's recovered memory notes\n\nHistorical excerpts from the reviewed local backup. Source line ranges can overlap.\n")
        spans = []
        for number, (path, first, last, encoded) in enumerate(rows, 1):
            body = base64.b64decode(encoded, validate=True)
            body.decode("utf-8")
            content.extend(f"\n## Excerpt {number}\n\nSource {json.dumps(path, ensure_ascii=False)}, lines {first} to {last}\n\n".encode())
            spans.append((len(content), body))
            content.extend(body)
            content.extend(b"\n")

        memory = workspace / "memory"
        if memory.resolve() != memory:
            raise ValueError("linked memory directory refused")
        memory.mkdir(mode=0o700, exist_ok=True)
        note = memory / "orion-recovered-v1.md"
        if not os.path.lexists(note):
            # Renaming a complete directory works without hard links. A populated
            # destination directory cannot be replaced by another directory rename.
            bundle = memory / "orion-recovery"
            note = bundle / "orion-recovered-v1.md"
            if not os.path.lexists(bundle):
                staged = temp / "ready"
                staged.mkdir(mode=0o700)
                with (staged / note.name).open("xb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                try:
                    staged.rename(bundle)
                except OSError:
                    if not os.path.lexists(bundle):
                        raise
            if bundle.resolve(strict=True) != bundle or not bundle.is_dir():
                raise ValueError("expected the private recovery note directory")
        saved = regular(note)
        if saved != content:
            raise ValueError("existing destination differs; it was preserved")
        if any(saved[offset:offset + len(body)] != body for offset, body in spans):
            raise ValueError("saved excerpt differs from database text")
        check_identity()
    return {"result":"KNOWLEDGE_PASS", "chunks_verified":len(rows), "identity_files_verified":4,
            "note":str(note), "note_sha256":sha(saved)}


if __name__ == "__main__":
    os.umask(0o077)
    try:
        print(json.dumps(recover(ROOT, ARCHIVE, ARCHIVE_HASH, MANIFEST_HASH), indent=2))
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.SubprocessError) as error:
        print("KNOWLEDGE_STOP", type(error).__name__, str(error) if not isinstance(error, subprocess.SubprocessError) else "SQLite reader failed")
        sys.exit(1)
