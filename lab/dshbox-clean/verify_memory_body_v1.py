"""One targeted agent turn after the preserved metadata-quote STOP."""
import fcntl
import getpass
import hashlib
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

import orion_chat_v2 as launcher
import finalize_read_v3 as saved

REPORTS = ("verification-report.json","quote-verification-v2.json","source-range-verification-v3.json")


def json_answer(text):
    text=text.strip()
    if text.startswith("```"):
        text=re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$","",text,flags=re.I)
    result=json.loads(text)
    if not isinstance(result,dict):raise ValueError("expected a JSON answer")
    return result


def body_line(note, spans):
    for start,end in spans:
        cursor=start
        for line in note[start:end].splitlines(keepends=True):
            text=line.decode("utf-8").strip()
            if (60<=len(line)<=1600 and len(re.findall(r"\w+",text))>=8
                    and not re.match(r"^(#|\x60{3}|Source\b)",text)
                    and not re.search(r"ORION_REDACTED|api.?key|password|\btoken\b|https?://",text,re.I)):
                return note[:cursor].count(b"\n")+1,text
            cursor+=len(line)
    raise ValueError("no suitable original memory-body line")


def verify(test):
    attempt=test/"body-verification-attempt-v1.json"
    if os.path.lexists(attempt):
        raise ValueError("targeted turn already attempted; existing evidence retained")
    source=launcher.CHAT/"home/.openclaw/workspace"
    oldtarget=test/"home/.openclaw/workspace"
    originals={n:launcher.regular(test/n) for n in REPORTS}
    original=json.loads(originals["verification-report.json"])
    final=json.loads(originals["source-range-verification-v3.json"])
    if original.get("exit")!=0 or final.get("result")!="READ_VERIFY_STOP" or final.get("quote_origin",{}).get("origin")!="metadata_only":
        raise ValueError("expected the completed metadata-only STOP evidence")
    launcher.checked_workspace(source);launcher.checked_workspace(oldtarget)
    note=launcher.regular(oldtarget/launcher.NOTE)
    spans=saved.source_spans(note)
    previous=launcher.tool_evidence(launcher.events(test/"home/.openclaw",None),oldtarget)
    oldreply=launcher.regular(test/"reply.txt").decode()
    oldanswer=json_answer(oldreply)
    user=launcher.regular(oldtarget/"USER.md").decode()
    nonce=launcher.regular(oldtarget/"read-proof.txt").decode().strip()
    prior=launcher.verify_reply(oldreply,previous,user,note.decode(),nonce,memory_spans=spans)
    if any(not v for k,v in prior.items() if k!="memory_excerpt_quote"):
        raise ValueError("an earlier USER, proof or tool-evidence check failed")
    offset,selected=body_line(note,spans)
    work=Path(tempfile.mkdtemp(prefix="orion-memory-body-",dir=launcher.CHAT.parent))
    target=work/"home/.openclaw/workspace"
    for name in launcher.HASHES:
        file=target/name;file.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copyfile(source/name,file)
    launcher.checked_workspace(target)
    (target/"MEMORY.md").write_text(launcher.POINTER)
    receipt=json.loads(launcher.regular(launcher.CHAT/"chat-session.json"))
    cfg=json.loads(json.dumps(receipt["config"]))
    cfg["agents"]["defaults"]["workspace"]=str(target)
    cfg["logging"]={"file":str(work/"app.log")}
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));cfg["gateway"]["port"]=sock.getsockname()[1]
    cfg["gateway"]["auth"]={"mode":"token","token":secrets.token_urlsafe(32)}
    config=target.parent/"openclaw.json";config.write_text(json.dumps(cfg))
    env=launcher.environment(work,target,config)
    result=launcher.call(env,target,120,"config","validate","--json")
    if result.returncode or json.loads(result.stdout).get("valid") is not True:
        raise ValueError("isolated configuration validation failed; no agent turn started")
    key=getpass.getpass("OpenRouter API key (hidden): ").strip()
    if not key:raise ValueError("empty key")
    env["OPENROUTER_API_KEY"]=key
    session=str(uuid.uuid4())
    prompt=(f"Use read on {launcher.NOTE} with offset={offset} and limit=1. "
            "This line is original recovered memory content. From the text returned by read, copy "
            "one exact 5 to 20 word phrase as a fact. Return only JSON with memory_fact and memory_quote, "
            "both containing the same verbatim phrase, preserving case and punctuation. "
            "Quote the line's content, excluding generated headings or source labels. "
            "If read fails, report that failure honestly. No file writes.")
    report={"result":"READ_VERIFY_STOP","additional_agent_turns":1,"test_directory":str(work),
            "reused_evidence":["USER.md successful read and quoted fact","random proof successful read and exact value"],
            "original_reports_sha256":{n:hashlib.sha256(b).hexdigest() for n,b in originals.items()}}
    with attempt.open("x") as f:
        json.dump({"test_directory":str(work),"status":"agent turn requested"},f)
        f.flush();os.fsync(f.fileno())
    print("One targeted memory-body turn. Allow up to six minutes.",flush=True)
    try:
        run=launcher.call(env,target,360,"agent","--local","--agent","main","--session-id",session,
                          "--model",launcher.MODEL,"--timeout","180","--message",prompt,"--json")
        evidence=launcher.tool_evidence(launcher.events(work/"home/.openclaw",session),target)
        report["new_memory_tools"]=launcher.public_evidence(evidence)
        reply=launcher.check_run(run)
        (work/"reply.txt").write_text(reply.replace(key,"[redacted]"))
        newanswer=json_answer(reply)
        combined=dict(oldanswer)
        combined.update(memory_fact=newanswer.get("memory_fact"),memory_quote=newanswer.get("memory_quote"))
        # USER and proof remain tied to their original successful results.
        # Memory must come from the NEW turn's successful result.
        inherited=[e for e in previous if e["target"] in ("USER.md","read-proof.txt")]
        combined_evidence=inherited+[e for e in evidence if e["target"]==launcher.NOTE]
        checks=launcher.verify_reply(json.dumps(combined),combined_evidence,user,note.decode(),nonce,memory_spans=spans)
        quote=newanswer.get("memory_quote")
        checks["selected_body_line"]=isinstance(quote,str) and len(quote.strip())>=16 and quote in selected
        report["checks"]=checks
        report["quote_origin"]=launcher.memory_quote_origin(quote,note,spans)
        launcher.checked_workspace(source);launcher.checked_workspace(oldtarget);launcher.checked_workspace(target)
        for name,raw in originals.items():
            if launcher.regular(test/name)!=raw:raise ValueError("original report changed")
        if checks and all(checks.values()):
            launcher.install_update(source)
            report["result"]="READ_VERIFY_PASS"
            with tempfile.NamedTemporaryFile(mode="w",dir=launcher.CHAT,delete=False) as f:
                file=Path(f.name);json.dump(report,f,indent=2);f.flush();os.fsync(f.fileno())
            file.replace(launcher.CHAT/"read-verification-v2.json")
            print("\nOrion's verified memory phrase (keep on your phone):\n"+quote.replace(key,"[redacted]"))
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        report["failure"]=type(error).__name__ if isinstance(error,subprocess.SubprocessError) else str(error).replace(key,"[redacted]")
    (work/"body-verification-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return 0 if report["result"]=="READ_VERIFY_PASS" else 1


if __name__=="__main__":
    os.umask(0o077)
    try:
        with (launcher.CHAT/"chat.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            sys.exit(verify(saved.TEST))
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print("READ_VERIFY_STOP",str(error),file=sys.stderr)
        sys.exit(1)
