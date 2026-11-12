"""Read-only checkpoint inventory. Emits metadata and hashes, never file contents."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import time

IDENTITY = {"SOUL.md", "IDENTITY.md", "AGENTS.md", "USER.md"}
CHUNK = 1024 * 1024


def inspect(checkpoint):
    initial = checkpoint.lstat()
    if not stat.S_ISREG(initial.st_mode):
        raise ValueError("Checkpoint must be a regular file.")
    deadline = time.monotonic() + 900

    def consume(stream, digest=None):
        total = 0
        while True:
            if time.monotonic() > deadline:
                raise ValueError("Inspection exceeded 15 minutes.")
            block = stream.read(CHUNK)
            if not block:
                return total
            total += len(block)
            if digest is not None:
                digest.update(block)

    names = set()
    identity = []
    databases = []
    counts = {"files": 0, "directories": 0, "links": 0, "other": 0}
    expanded = 0
    digest = hashlib.sha256()
    with checkpoint.open("rb") as raw:
        pinned = os.fstat(raw.fileno())
        if (pinned.st_dev, pinned.st_ino) != (initial.st_dev, initial.st_ino):
            raise ValueError("Checkpoint changed before opening.")
        consume(raw, digest)
        raw.seek(0)
        with gzip.GzipFile(fileobj=raw, mode="rb") as compressed:
            with tarfile.open(fileobj=compressed, mode="r|") as archive:
                for member in archive:
                    name = PurePosixPath(member.name)
                    if name.is_absolute() or ".." in name.parts:
                        raise ValueError("Archive contains an unsafe member path.")
                    canonical = str(name)
                    if canonical in names:
                        raise ValueError("Archive contains duplicate member paths.")
                    names.add(canonical)
                    if len(names) > 1_000_000:
                        raise ValueError("Archive exceeds the inventory entry limit.")
                    expanded += member.size
                    if expanded > 16 * 1024**3:
                        raise ValueError("Archive exceeds the 16 GiB inspection limit.")
                    if member.isfile():
                        counts["files"] += 1
                        if name.name in IDENTITY:
                            fingerprint = hashlib.sha256()
                            with archive.extractfile(member) as source:
                                consume(source, fingerprint)
                            identity.append({"member": canonical, "bytes": member.size,
                                             "sha256": fingerprint.hexdigest()})
                        if name.name.endswith((".sqlite", ".sqlite3", ".db", "-wal", "-shm")):
                            databases.append({"member": canonical, "bytes": member.size})
                    elif member.isdir():
                        counts["directories"] += 1
                    elif member.issym() or member.islnk():
                        counts["links"] += 1
                    else:
                        counts["other"] += 1
            # tar EOF can precede gzip EOF. Drain to verify the gzip trailer/CRC.
            consume(compressed)
        final = os.fstat(raw.fileno())
    current = checkpoint.lstat()
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if stamp(initial) != stamp(final) or stamp(final) != stamp(current):
        raise ValueError("Checkpoint changed during inspection.")
    return {"result": "ARCHIVE_STRUCTURE_PASS", "archive_bytes": initial.st_size,
            "archive_sha256": digest.hexdigest(), "gzip_crc": "ok",
            "counts": counts, "declared_file_bytes": expanded,
            "database_candidates": databases, "identity_files": identity,
            "missing_identity_names": sorted(IDENTITY - {PurePosixPath(i["member"]).name for i in identity}),
            "link_review_required": counts["links"] > 0 or counts["other"] > 0,
            "provenance": "Newly measured checksum; compare with any independently retained checksum.",
            "pending": ["independent recovery copy", "isolated restore and SQLite checks",
                        "table and column export allowlist", "credential review", "export approval"],
            "upload_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.checkpoint), indent=2))
    except (OSError, ValueError, tarfile.TarError, EOFError) as error:
        # Exception strings can contain attacker-controlled member names or file data.
        print(json.dumps({"result": "STOP", "failure_type": type(error).__name__,
                          "reason": str(error) if isinstance(error, ValueError) else
                          "Checkpoint could not be read or archive validation failed.",
                          "upload_ready": False}))
        raise SystemExit(1)
