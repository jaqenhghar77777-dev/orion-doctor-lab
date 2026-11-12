"""One final local recheck using original source-chunk byte ranges."""
import base64
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

import orion_chat_v2 as launcher

TEST = Path("/root/orion-read-test-szbb572y")
ARCHIVE = Path("/root/orion-export-review-BYY7Km/orion_sanitized_rehearsal_v1.tar.gz")
ARCHIVE_HASH = "d991442d8e5175dd2d38eb7402c148507b93d855a5e91d4ffe6038c059bfffd3"
MANIFEST_HASH = "38cc930e6aa93cb14b0eb6f7f0e4b9babf51ab1bf95ceef34cd70d554e7864ad"
MAIN = "agents/main/agent/openclaw-agent.sqlite"
READ = """
const {DatabaseSync}=require('node:sqlite');
const db=new DatabaseSync(process.argv[1],{readOnly:true});
try {
 db.exec('PRAGMA query_only=ON');
 const rows=db.prepare('SELECT path,start_line,end_line,CAST(text AS BLOB) AS body FROM memory_index_chunks ORDER BY path,start_line,end_line,id,chunk_rowid').all();
 process.stdout.write(JSON.stringify(rows.map(r=>[r.path,r.start_line,r.end_line,Buffer.from(r.body).toString('base64')])));
} finally {db.close();}
"""


def reconstruct(rows):
    content=bytearray(b"# Orion's recovered memory notes\n\nHistorical excerpts from the reviewed local backup. Source line ranges can overlap.\n")
    spans=[]
    for index,(path,first,last,encoded) in enumerate(rows,1):
        body=base64.b64decode(encoded,validate=True)
        body.decode("utf-8")
        content.extend(f"\n## Excerpt {index}\n\nSource {json.dumps(path,ensure_ascii=False)}, lines {first} to {last}\n\n".encode())
        start=len(content);content.extend(body);spans.append((start,len(content)))
        content.extend(b"\n")
    return bytes(content),spans


def source_spans(note):
    archive=launcher.regular(ARCHIVE)
    if hashlib.sha256(archive).hexdigest()!=ARCHIVE_HASH:
        raise ValueError("reviewed archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as tar:
        def read(name):
            member=tar.getmember(name)
            if not member.isfile():raise ValueError("unexpected archive member")
            return tar.extractfile(member).read()
        manifest=read("manifest.json")
        if hashlib.sha256(manifest).hexdigest()!=MANIFEST_HASH:
            raise ValueError("reviewed manifest checksum mismatch")
        database=read(MAIN)
    indexed={f["path"]:f for f in json.loads(manifest)["files"]}
    if hashlib.sha256(database).hexdigest()!=indexed[MAIN]["sha256"]:
        raise ValueError("reviewed database checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="orion-source-ranges-") as directory:
        file=Path(directory)/"source.sqlite";file.write_bytes(database)
        run=subprocess.run([shutil.which("node"),"--no-warnings","--input-type=commonjs","-e",READ,str(file)],
                           cwd=directory,env={"PATH":os.environ["PATH"],"HOME":directory,"TMPDIR":directory,
                                             "NODE_DISABLE_COMPILE_CACHE":"1"},
                           capture_output=True,text=True,timeout=60)
        if run.returncode:raise ValueError("source memory query failed")
        rows=json.loads(run.stdout)
    if len(rows)!=70:raise ValueError("expected 70 reviewed chunks")
    rebuilt,spans=reconstruct(rows)
    if rebuilt!=note:raise ValueError("saved note differs from reconstructed archive chunks")
    return spans


def finalize(test):
    source=launcher.CHAT/"home/.openclaw/workspace"
    target=test/"home/.openclaw/workspace"
    originals={name:launcher.regular(test/name) for name in ("verification-report.json","quote-verification-v2.json")}
    report0=json.loads(originals["verification-report.json"])
    if report0.get("test_directory")!=str(test) or report0.get("exit")!=0:
        raise ValueError("expected completed isolated evidence")
    launcher.checked_workspace(source);launcher.checked_workspace(target)
    reply=launcher.regular(test/"reply.txt").decode()
    payload=reply.strip()
    if payload.startswith("```"):
        payload=re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$","",payload,flags=re.I)
    answer=json.loads(payload)
    if not isinstance(answer,dict):raise ValueError("expected saved JSON answer")
    note=launcher.regular(target/launcher.NOTE)
    spans=source_spans(note)
    evidence=launcher.tool_evidence(launcher.events(test/"home/.openclaw",None),target)
    user=launcher.regular(target/"USER.md").decode()
    nonce=launcher.regular(target/"read-proof.txt").decode().strip()
    checks=launcher.verify_reply(reply,evidence,user,note.decode(),nonce,memory_spans=spans)
    origin=launcher.memory_quote_origin(answer.get("memory_quote"),note,spans)
    report={"result":"READ_VERIFY_STOP","model_requests":0,"source_chunks_verified":len(spans),
            "note_reconstructed_byte_exact":True,"quote_origin":origin,"checks":checks,
            "original_reports_sha256":{n:hashlib.sha256(b).hexdigest() for n,b in originals.items()}}
    for name,data in originals.items():
        if launcher.regular(test/name)!=data:raise ValueError("original report changed")
    if checks and all(checks.values()):
        launcher.install_update(source)
        report["result"]="READ_VERIFY_PASS"
        with tempfile.NamedTemporaryFile(mode="w",dir=launcher.CHAT,delete=False) as f:
            staged=Path(f.name);json.dump(report,f,indent=2);f.flush();os.fsync(f.fileno())
        staged.replace(launcher.CHAT/"read-verification-v2.json")
    output=test/"source-range-verification-v3.json"
    serialized=json.dumps(report,indent=2)+"\n"
    try:
        with output.open("x") as f:f.write(serialized)
    except FileExistsError:
        if launcher.regular(output).decode()!=serialized:raise ValueError("existing final report preserved")
    print(serialized)
    return 0 if report["result"]=="READ_VERIFY_PASS" else 1


if __name__=="__main__":
    os.umask(0o077)
    try:
        with (launcher.CHAT/"chat.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            sys.exit(finalize(TEST))
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print("READ_VERIFY_STOP",str(error),file=sys.stderr)
        sys.exit(1)
