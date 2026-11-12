"""Verify and package only the reviewed candidate; no network or OpenClaw command."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile

EXPORT = Path("/root/orion-export-review-BYY7Km")
RESTORE = Path("/root/orion-real-rehearsal-9a_4zlyq")
ARCHIVE_HASH = "daccf87f3dc4173d7ee52e300d33546e82d73d2cdf279a69c57f8f22df06707c"
DATABASES = {"agents/main/agent/openclaw-agent.sqlite",
             "agents/openclaw/agent/openclaw-agent.sqlite", "state/openclaw.sqlite"}
IDENTITIES = {"workspace/" + name for name in ("SOUL.md", "IDENTITY.md", "AGENTS.md", "USER.md")}
REQUIRED = DATABASES | IDENTITIES
MARKER = "[ORION_REDACTED_CREDENTIAL]"
AUDIT = r"""
const fs=require('node:fs'),path=require('node:path');
const {DatabaseSync}=require('node:sqlite');
const {zstdDecompressSync}=require('node:zlib');
const request=JSON.parse(fs.readFileSync(0,'utf8'));
const marker='[ORION_REDACTED_CREDENTIAL]';
const canonical=value=>JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?
  Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
const event=row=>JSON.parse(row.event_json??zstdDecompressSync(row.event_zstd,{maxOutputLength:64*1024*1024}).toString('utf8'));
let current='source';
function assertRedaction(before,after) {
  if(canonical(before)===canonical(after))return;
  if(typeof after==='string'&&after.includes(marker)) {
    if(typeof before!=='string') {
      if(after===marker)return;
      throw Error('UNCLASSIFIED_CONTENT_CHANGE');
    }
    const parts=after.split(marker);
    if(!before.startsWith(parts[0])||!before.endsWith(parts.at(-1)))throw Error('UNCLASSIFIED_CONTENT_CHANGE');
    let position=parts[0].length;
    for(const part of parts.slice(1,-1)) {
      const found=before.indexOf(part,position);
      if(found<0)throw Error('UNCLASSIFIED_CONTENT_CHANGE');
      position=found+part.length;
    }
    if(position>before.length-parts.at(-1).length)throw Error('UNCLASSIFIED_CONTENT_CHANGE');
    return;
  }
  if(Array.isArray(before)&&Array.isArray(after)&&before.length===after.length) {
    for(let i=0;i<before.length;i++)assertRedaction(before[i],after[i]);
    return;
  }
  if(before&&after&&typeof before==='object'&&typeof after==='object'&&
     !Array.isArray(before)&&!Array.isArray(after)) {
    const a=Object.keys(before).sort(),b=Object.keys(after).sort();
    if(canonical(a)!==canonical(b))throw Error('REDACTION_OBJECT_KEYS_CHANGED');
    for(const key of a)assertRedaction(before[key],after[key]);
    return;
  }
  throw Error('UNCLASSIFIED_CONTENT_CHANGE');
}
const opened=[];
try {
  const source=new DatabaseSync(request.source,{readOnly:true});opened.push(source);
  const candidate=new DatabaseSync(request.candidate,{readOnly:true});opened.push(candidate);
  const rows=db=>db.prepare('SELECT session_id,seq,event_json,event_zstd FROM transcript_events ORDER BY session_id,seq').all();
  const a=rows(source),b=rows(candidate);
  if(a.length!==b.length)throw Error('TRANSCRIPT_COUNT_CHANGED');
  let eventsChanged=0;
  current='transcript comparison';
  for(let i=0;i<a.length;i++) {
    if(a[i].session_id!==b[i].session_id||a[i].seq!==b[i].seq)throw Error('TRANSCRIPT_IDENTITY_CHANGED');
    const before=event(a[i]),after=event(b[i]);
    if(canonical(before)!==canonical(after)){assertRedaction(before,after);eventsChanged++;}
  }
  current='memory comparison';
  const memory=db=>db.prepare('SELECT id,text FROM memory_index_chunks ORDER BY id').all();
  const ma=memory(source),mb=memory(candidate);
  if(ma.length!==mb.length)throw Error('MEMORY_COUNT_CHANGED');
  let memoryChanged=0;
  for(let i=0;i<ma.length;i++) {
    if(ma[i].id!==mb[i].id)throw Error('MEMORY_IDENTITY_CHANGED');
    if(ma[i].text!==mb[i].text){assertRedaction(ma[i].text,mb[i].text);memoryChanged++;}
  }
  process.stdout.write(JSON.stringify({transcript_events:a.length,changed_transcript_events:eventsChanged,
    memory_chunks:ma.length,changed_memory_chunks:memoryChanged,
    change_classification:'credential-marker redactions; record identities and order retained'}));
}catch(error){
  const known=new Set(['REDACTION_OBJECT_KEYS_CHANGED','UNCLASSIFIED_CONTENT_CHANGE',
    'TRANSCRIPT_COUNT_CHANGED','TRANSCRIPT_IDENTITY_CHANGED','MEMORY_COUNT_CHANGED','MEMORY_IDENTITY_CHANGED']);
  process.stdout.write(JSON.stringify({failure:known.has(error.message)?error.message:'REDACTION_CHECK_ERROR',stage:current}));
  process.exitCode=1;
}finally{for(const db of opened)db.close();}
"""


def sha(file):
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def regular(root, relative):
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or "\\" in relative or str(name) != relative:
        raise ValueError("Invalid manifest path.")
    file = root / relative
    if file.resolve(strict=True) != file or not stat.S_ISREG(file.lstat().st_mode):
        raise ValueError("Candidate must contain regular files without symlinks.")
    return file


def package(export=EXPORT, restore=RESTORE):
    export = export.resolve(strict=True)
    candidate = export / "candidate"
    if candidate.resolve(strict=True) != candidate:
        raise ValueError("Unexpected candidate directory.")
    review = json.loads((export / "export-review.json").read_text())
    manifest_file = regular(candidate, "manifest.json")
    manifest_bytes = manifest_file.read_bytes()
    manifest = json.loads(manifest_bytes)
    if review.get("result") != "EXPORT_CANDIDATE_REVIEW_REQUIRED" or review.get("candidate") != str(candidate):
        raise ValueError("Successful candidate review report required.")
    if manifest.get("archive_sha256") != ARCHIVE_HASH or manifest.get("upload_ready") is not False:
        raise ValueError("Unexpected candidate provenance or gate.")
    entries = manifest["files"]
    indexed = {item["path"]: item for item in entries}
    if len(indexed) != len(entries) or set(indexed) != REQUIRED or review["files"] != 7:
        raise ValueError("Expected exactly the reviewed three databases and four identity files.")
    actual = set()
    for directory, directories, filenames in os.walk(candidate, followlinks=False):
        for name in directories:
            if (Path(directory) / name).is_symlink():
                raise ValueError("Candidate directory contains a symlink.")
        for name in filenames:
            actual.add((Path(directory) / name).relative_to(candidate).as_posix())
    if actual != REQUIRED | {"manifest.json"}:
        raise ValueError("Candidate contains unmanifested files.")
    for name, entry in indexed.items():
        file = regular(candidate, name)
        if file.stat().st_size != entry["bytes"] or sha(file) != entry["sha256"]:
            raise ValueError("Candidate file differs from the reviewed manifest.")
    for identity in review["identity_files"]:
        if identity["path"] not in IDENTITIES or indexed[identity["path"]]["sha256"] != identity["sha256"]:
            raise ValueError("Identity review differs from the manifest.")
    if {i["path"] for i in review["identity_files"]} != IDENTITIES:
        raise ValueError("Incomplete identity review.")
    source = restore / "restored/orion-beta-trial-20261107/.openclaw/agents/main/agent/openclaw-agent.sqlite"
    if source.resolve(strict=True) != source:
        raise ValueError("Unexpected disposable source path.")
    env = {k: os.environ[k] for k in ("PATH", "LANG", "LD_LIBRARY_PATH") if k in os.environ}
    result = subprocess.run(["node", "--no-warnings", "-e", AUDIT], cwd=export, env=env,
                            input=json.dumps({"source": str(source), "candidate": str(candidate / "agents/main/agent/openclaw-agent.sqlite")}),
                            text=True, capture_output=True, timeout=180)
    audit = json.loads(result.stdout)
    if result.returncode or "failure" in audit:
        raise ValueError("Redaction review stopped: " + audit.get("failure", "checker failure"))
    changes = {(c.get("database"), c.get("table")): c for c in review["changed_tables"]}
    for table, field in [("transcript_events", "changed_transcript_events"),
                         ("memory_index_chunks", "changed_memory_chunks")]:
        expected = changes.get(("agents/main/agent/openclaw-agent.sqlite", table), {}).get("modifiedRows", 0)
        if audit[field] != expected:
            raise ValueError("Redaction counts differ from the candidate review.")
    if manifest_file.read_bytes() != manifest_bytes:
        raise ValueError("Manifest changed during review.")

    archive = export / "orion_sanitized_rehearsal_v1.tar.gz"
    with archive.open("xb") as output:
        os.chmod(archive, 0o600)
        with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                for name in sorted(REQUIRED | {"manifest.json"}):
                    file = regular(candidate, name)
                    with file.open("rb") as stream:
                        before = os.fstat(stream.fileno())
                        header = tarfile.TarInfo(name)
                        header.size = before.st_size
                        header.mode = 0o600
                        tar.addfile(header, stream)
                        if stamp(before) != stamp(os.fstat(stream.fileno())):
                            raise ValueError("Candidate changed while packing.")
        output.flush()
        os.fsync(output.fileno())
    expected = {name: item["sha256"] for name, item in indexed.items()}
    expected["manifest.json"] = hashlib.sha256(manifest_bytes).hexdigest()
    seen = set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or member.name not in expected or member.name in seen:
                raise ValueError("Packed archive member differs.")
            seen.add(member.name)
            digest = hashlib.sha256()
            with tar.extractfile(member) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected[member.name]:
                raise ValueError("Packed archive checksum differs.")
    if seen != set(expected):
        raise ValueError("Packed archive is incomplete.")
    receipt = {"result": "PACKAGED_REVIEW_REQUIRED", "archive": str(archive),
               "archive_sha256": sha(archive), "bytes": archive.stat().st_size,
               "manifest_sha256": expected["manifest.json"], "regular_files": len(seen),
               "redaction_review": audit, "github_cli_available": shutil.which("gh") is not None,
               "upload_ready": False}
    with (export / "package-review.json").open("x") as out:
        os.chmod(out.name, 0o600)
        json.dump(receipt, out, indent=2)
        out.write("\n")
    return receipt


if __name__ == "__main__":
    os.umask(0o077)
    try:
        print(json.dumps(package(), indent=2))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError, EOFError) as error:
        print(json.dumps({"result": "STOP", "failure_type": type(error).__name__,
                          "reason": str(error) if isinstance(error, ValueError) else "Packaging failed; retain the local candidate.",
                          "upload_ready": False}, indent=2))
        raise SystemExit(1)
