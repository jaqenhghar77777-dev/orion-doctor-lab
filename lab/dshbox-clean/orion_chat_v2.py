"""Verify actual file-tool evidence before updating the isolated Orion chat."""
import argparse
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

sys.path.insert(0, "/root/orion-dshbox-chat-v1")

from openrouter_reply_v1 import CLI, HASHES, MODEL, NOTE, checked_workspace, result_text, validator_issues

CHAT = Path("/root/orion-dshbox-chat-v1")
POINTER = ("# Recovered knowledge\n\n"
           "The restored user profile is USER.md in this workspace.\n"
           "Historical knowledge was recovered into " + NOTE + ".\n"
           "Use the read tool with these workspace-relative paths to consult the actual files.\n"
           "Report a file-access error accurately when a tool fails.\n")
GUIDANCE = ("Workspace reference for this turn: read USER.md for the user profile. "
            "Recovered historical excerpts are in " + NOTE + ". "
            "Use workspace-relative read paths. Ground claims about file contents or access in tool results.\n\n")


def regular(path):
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError("expected an unlinked regular file: " + path.name)
    return path.read_bytes()


def environment(base, workspace, config):
    home = base / "home"
    home.mkdir(mode=0o700, exist_ok=True)
    env = {"PATH":os.environ["PATH"],"LANG":"C.UTF-8","HOME":str(home),"OPENCLAW_HOME":str(home),
           "OPENCLAW_STATE_DIR":str(home / ".openclaw"),"OPENCLAW_CONFIG_PATH":str(config),
           "OPENCLAW_WORKSPACE_DIR":str(workspace),"OPENCLAW_SKIP_CHANNELS":"1",
           "OPENCLAW_DISABLE_BONJOUR":"1","NODE_DISABLE_COMPILE_CACHE":"1","NO_COLOR":"1","CI":"1"}
    for name in ("TMPDIR","XDG_CONFIG_HOME","XDG_STATE_HOME","XDG_DATA_HOME","XDG_CACHE_HOME","XDG_RUNTIME_DIR"):
        folder = base / name.lower()
        if folder.resolve() != folder:
            raise ValueError("linked runtime directory")
        folder.mkdir(mode=0o700, exist_ok=True)
        env[name] = str(folder)
    return env


def call(env, workspace, seconds, *args):
    node, timeout = shutil.which("node"), shutil.which("timeout")
    if not node or not timeout:
        raise ValueError("Node and GNU timeout required")
    return subprocess.run([timeout,"--kill-after=10s",str(seconds),node,str(CLI),*args],
                          cwd=workspace,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True)


AUDIT = r"""
const fs=require('node:fs'), {DatabaseSync}=require('node:sqlite'),{zstdDecompressSync}=require('node:zlib');
const db=new DatabaseSync(process.argv[1],{readOnly:true});
try{
 db.exec('PRAGMA query_only=ON');
 if(!process.argv[2] && db.prepare('SELECT count(DISTINCT session_id) AS n FROM transcript_events').get().n>1)throw Error('MULTIPLE_AUDIT_SESSIONS');
 const rows=db.prepare('SELECT event_json,event_zstd FROM transcript_events'+(process.argv[2]?' WHERE session_id=?':'')+' ORDER BY seq').all(...(process.argv[2]?[process.argv[2]]:[]));
 if(rows.length>20000)throw Error('AUDIT_LIMIT');
 process.stdout.write(JSON.stringify(rows.map(r=>JSON.parse(r.event_json??
    zstdDecompressSync(r.event_zstd,{maxOutputLength:16*1024*1024}).toString('utf8')))));
}finally{db.close();}
"""


def events(state, session):
    file = state / "agents/main/agent/openclaw-agent.sqlite"
    if not file.exists():
        return []
    with tempfile.TemporaryDirectory(prefix="orion-read-evidence-") as tmp:
        copy = Path(tmp) / "copy.sqlite"
        for suffix in ("", "-wal"):
            source = Path(str(file)+suffix)
            if source.exists():
                regular(source)
                before = source.stat()
                shutil.copyfile(source,Path(str(copy)+suffix))
                after = source.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                    raise ValueError("history changed during audit")
        run = subprocess.run([shutil.which("node"),"--no-warnings","--input-type=commonjs","-e",AUDIT,str(copy)]+([session] if session else []),
                             cwd=tmp,env={"PATH":os.environ["PATH"],"HOME":tmp,"TMPDIR":tmp,
                                          "NODE_DISABLE_COMPILE_CACHE":"1"},capture_output=True,text=True,timeout=60)
        if run.returncode:
            raise ValueError("read-only transcript evidence unavailable")
        return json.loads(run.stdout)


def text_content(message):
    value = message.get("content",[])
    if isinstance(value,str):
        return value
    return "\n".join(p.get("text","") for p in value if isinstance(p,dict) and p.get("type")=="text")


def tool_evidence(records, workspace):
    calls, results = {}, {}
    for event in records:
        message = event.get("message",{})
        if not isinstance(message,dict):
            continue
        if message.get("role")=="assistant" and isinstance(message.get("content"),list):
            for item in message["content"]:
                if isinstance(item,dict) and item.get("type")=="toolCall":
                    args = item.get("arguments") or {}
                    if isinstance(args,str):
                        try: args=json.loads(args)
                        except ValueError: args={}
                    raw = args.get("path",args.get("file_path","")) if isinstance(args,dict) else ""
                    target = str(raw)
                    try:
                        target = str((workspace / raw).relative_to(workspace)) if not Path(raw).is_absolute() else str(Path(raw).relative_to(workspace))
                    except (ValueError,TypeError):
                        target = "other-path"
                    if not isinstance(item.get("id"),str) or not item["id"]:
                        continue
                    calls[item["id"]] = {"tool":str(item.get("name","")),
                                            "target":target if target in ("USER.md",NOTE,"read-proof.txt") else "other-path"}
        if message.get("role")=="toolResult" and isinstance(message.get("toolCallId"),str):
            results[message["toolCallId"]] = message
    summary = []
    for key, item in calls.items():
        result = results.get(key)
        content = text_content(result) if result else ""
        failed = result is not None and (result.get("isError") is True or
                  bool(re.search(r"^\s*(?:Error:|ENOENT|EACCES|EPERM|Path escapes sandbox root|File not found)",content,re.I)))
        code = next((x for x in ("ENOENT","EACCES","EPERM","Path escapes sandbox root","File not found")
                     if x.lower() in content.lower()),None) if failed else None
        summary.append({**item,"status":"NO_RESULT" if result is None else "ERROR" if failed else "SUCCESS",
                        **({"error":code or "TOOL_ERROR"} if failed else {}), "_text":content})
    return summary


def normalized_quote(value):
    # Preserve words, punctuation and case. Line wrapping alone has no semantic effect.
    return " ".join(value.split())


def verify_reply(reply, evidence, user, note, nonce):
    payload = reply.strip()
    if payload.startswith("```"):
        payload = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$","",payload,flags=re.I)
    try: answer=json.loads(payload)
    except ValueError: return {"reply_json":False}
    if not isinstance(answer,dict): return {"reply_json":False}
    def quote_match(value, content):
        return isinstance(value,str) and len(value.strip())>=16 and normalized_quote(value) in normalized_quote(content)
    reads = {}
    for item in evidence:
        if item["tool"].split(".")[-1]=="read" and item["status"]=="SUCCESS":
            reads.setdefault(item["target"],[]).append(item.get("_text",""))
    def from_read(quote, target):
        return isinstance(quote,str) and any(normalized_quote(quote) in normalized_quote(body) for body in reads.get(target,[]))
    bodies = re.split(r"\n## Excerpt \d+\n\nSource [^\n]*\n\n",note)[1:]
    return {"reply_json":True,"user_read":"USER.md" in reads,"memory_read":NOTE in reads,
            "proof_read":"read-proof.txt" in reads,"proof_value":answer.get("proof")==nonce and any(nonce in body for body in reads.get("read-proof.txt",[])),
            "user_fact_quote":quote_match(answer.get("user_quote"),user) and from_read(answer.get("user_quote"),"USER.md"),
            "memory_excerpt_quote":any(quote_match(answer.get("memory_quote"),b) for b in bodies) and from_read(answer.get("memory_quote"),NOTE),
            "user_fact_identified":answer.get("user_fact")==answer.get("user_quote") and isinstance(answer.get("user_fact"),str),
            "memory_fact_identified":answer.get("memory_fact")==answer.get("memory_quote") and isinstance(answer.get("memory_fact"),str)}


def public_evidence(evidence):
    return [{k:v for k,v in item.items() if k!="_text"} for item in evidence]


def collect_message(read=input):
    print("\nPaste or type one message. Finish with /send on a line by itself; /cancel discards it; /quit leaves.",flush=True)
    lines=[]
    while True:
        try: line=read()
        except EOFError: return None
        if line=="/quit": return None
        if line=="/cancel": return ""
        if line=="/send": return "\n".join(lines)
        lines.append(line)


def check_run(run):
    if run.returncode:
        raw = run.stdout + "\n" + run.stderr
        codes = [("OWNERSHIP_REFUSAL", r"GatewayLockNamespaceError|offline maintenance|state lease|already running"),
                 ("KEY_REJECTED", r"\b401\b|invalid api key|no api key|no auth credentials"),
                 ("RATE_LIMIT", r"\b429\b|rate.limit"), ("MODEL_UNAVAILABLE", r"no endpoints|unknown model|\b503\b")]
        code = next((name for name,pattern in codes if re.search(pattern,raw,re.I)), "TURN_FAILED")
        if run.returncode in (124,137): code = "TIMEOUT"
        raise ValueError(code + "; exit " + str(run.returncode))
    return result_text(json.loads(run.stdout))


def install_update(workspace):
    checked_workspace(workspace)
    index = workspace / "MEMORY.md"
    if not os.path.lexists(index):
        with index.open("x") as f:
            f.write(POINTER)
            f.flush()
            os.fsync(f.fileno())
    else:
        regular(index)
    destination = CHAT / "orion_chat_v2.py"
    content = Path(__file__).read_bytes()
    if Path(__file__).resolve() != destination:
        with tempfile.NamedTemporaryFile(dir=CHAT,delete=False) as f:
            staged=Path(f.name);f.write(content);f.flush();os.fsync(f.fileno())
        staged.replace(destination)


def verify(workspace, receipt):
    checked_workspace(workspace)
    report={"result":"READ_VERIFY_STOP","old_session_tools":public_evidence(tool_evidence(
        events(CHAT / "home/.openclaw",receipt["session_id"]),workspace))}
    test = Path(tempfile.mkdtemp(prefix="orion-read-test-",dir=CHAT.parent))
    report["test_directory"]=str(test)
    target = test / "home/.openclaw/workspace"
    for name in HASHES:
        file=target/name;file.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        shutil.copyfile(workspace/name,file)
    checked_workspace(target)
    (target/"MEMORY.md").write_text(POINTER)
    nonce=secrets.token_hex(16)
    (target/"read-proof.txt").write_text(nonce+"\n")
    config=test/"home/.openclaw/openclaw.json"
    cfg=json.loads(json.dumps(receipt["config"]))
    cfg["agents"]["defaults"]["workspace"]=str(target)
    cfg["logging"]={"file":str(test/"app.log")}
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        cfg["gateway"]["port"]=sock.getsockname()[1]
    cfg["gateway"]["auth"]={"mode":"token","token":secrets.token_urlsafe(32)}
    config.write_text(json.dumps(cfg))
    env=environment(test,target,config)
    validated=call(env,target,120,"config","validate","--json")
    if validated.returncode or json.loads(validated.stdout).get("valid") is not True:
        report["validation_issues"]=validator_issues(validated,cfg["gateway"])
    else:
        key=getpass.getpass("OpenRouter API key (hidden): ").strip()
        if not key: raise ValueError("empty key")
        env["OPENROUTER_API_KEY"]=key
        session=str(uuid.uuid4())
        prompt=(GUIDANCE+"Verification task. Invoke read separately for USER.md, the first 32 lines of "+
                NOTE+", and read-proof.txt. Return only a JSON object with user_fact and memory_fact "
                "(each one specific fact copied verbatim from that file), user_quote and memory_quote "
                "(repeat the same fact verbatim, each 5 to 20 words, preserving punctuation), "
                "and proof (the exact value read from read-proof.txt). If a read fails, explain the "
                "failure and do not invent values. No file writes.")
        print("One isolated verification turn. Allow up to six minutes.",flush=True)
        run=call(env,target,360,"agent","--local","--agent","main","--session-id",session,
                 "--model",MODEL,"--timeout","180","--message",prompt,"--json")
        evidence=tool_evidence(events(test/"home/.openclaw",session),target)
        report["isolated_tools"]=public_evidence(evidence)
        report["exit"]=run.returncode
        try:
            reply=check_run(run)
            (test/"reply.txt").write_text(reply.replace(key,"[redacted]"))
            report["checks"]=verify_reply(reply,evidence,(target/"USER.md").read_text(),(target/NOTE).read_text(),nonce)
            if report["checks"] and all(report["checks"].values()):
                install_update(workspace)
                report["result"]="READ_VERIFY_PASS"
                (CHAT/"read-verification-v2.json").write_text(json.dumps(report,indent=2))
                print("\nOrion's verification answer (keep the contents on your phone):\n"+reply.replace(key,"[redacted]"),flush=True)
        except (ValueError,KeyError) as error:
            report["failure"]=str(error).replace(key,"[redacted]")
    checked_workspace(workspace)
    checked_workspace(target)
    (test/"verification-report.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return 0 if report["result"]=="READ_VERIFY_PASS" else 1


def chat(workspace, receipt):
    config=CHAT/"home/.openclaw/openclaw.json"
    env=environment(CHAT,workspace,config)
    key=getpass.getpass("OpenRouter API key (hidden): ").strip()
    if not key: raise ValueError("empty key")
    env["OPENROUTER_API_KEY"]=key
    print("CHAT_READY — multiline composer enabled; saved session retained.")
    while True:
        prompt=collect_message()
        if prompt is None: break
        if not prompt.strip(): continue
        print("Orion is thinking...",flush=True)
        run=call(env,workspace,360,"agent","--local","--agent","main","--session-id",receipt["session_id"],
                 "--model",MODEL,"--timeout","180","--message",GUIDANCE+prompt,"--json")
        checked_workspace(workspace)
        reply=check_run(run)
        print("\nOrion: "+reply.replace(key,"[redacted]"),flush=True)
    print("CHAT_CLOSED — saved session retained.")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    os.umask(0o077)
    if not sys.stdin.isatty(): raise ValueError("interactive DSHBox terminal required")
    if CHAT.resolve(strict=True)!=CHAT: raise ValueError("linked chat directory")
    with (CHAT/"chat.lock").open("a") as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError("close the other chat launcher first")
        state=CHAT/"home/.openclaw";workspace=state/"workspace"
        checked_workspace(workspace)
        receipt=json.loads(regular(CHAT/"chat-session.json"))
        if receipt.get("format")!="orion-dshbox-chat-v1": raise ValueError("unexpected saved chat format")
        uuid.UUID(receipt["session_id"])
        if json.loads(regular(state/"openclaw.json"))!=receipt["config"]: raise ValueError("chat config changed")
        meta=json.loads((CLI.parent/"package.json").read_text())
        if (meta["name"],meta["version"])!=("openclaw","2026.11.5-beta.1"): raise ValueError("unexpected runtime")
        if args.verify: return verify(workspace,receipt)
        if not (CHAT/"read-verification-v2.json").is_file():
            raise ValueError("run --verify and obtain READ_VERIFY_PASS first")
        chat(workspace,receipt)
    return 0


if __name__=="__main__":
    try: sys.exit(main())
    except KeyboardInterrupt:
        print("\nCHAT_STOP — interrupted; saved session retained.")
        sys.exit(130)
    except (OSError,ValueError,KeyError,TypeError,EOFError,subprocess.SubprocessError) as error:
        print("CHAT_STOP",str(error),file=sys.stderr)
        sys.exit(1)
