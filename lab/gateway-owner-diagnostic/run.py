"""One real Gateway, one explicit session creation and one message, all fictional."""
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

ROOT = Path("/home/replay")
STATE = ROOT / ".openclaw"
CLI = "/opt/beta/node_modules/openclaw/openclaw.mjs"
REPORT = {"result":"STOP", "fixture":"fictional-only", "create_calls":0,"send_calls":0}
children = []


def call(*args, seconds=90):
    p = subprocess.run(["timeout","--kill-after=5s",str(seconds),"node",CLI,*args],
                       env=ENV,cwd=WORK,capture_output=True,text=True,timeout=seconds+10)
    if p.returncode:
        # All inputs, tokens and model data are generated inside this networkless container.
        raise RuntimeError("CLI exit "+str(p.returncode)+": "+(p.stderr+p.stdout)[-2200:])
    text = p.stdout
    decoder = json.JSONDecoder()
    for i,c in enumerate(text):
        if c == "{":
            try:
                value, end = decoder.raw_decode(text[i:])
                if not text[i+end:].strip():
                    return value
            except ValueError:
                pass
    raise RuntimeError("CLI returned no JSON object")


def health():
    c = http.client.HTTPConnection("127.0.0.1",18080,timeout=1)
    try:
        c.request("GET","/healthz")
        r=c.getresponse()
        return r.status==200 and json.loads(r.read(4096)).get("ok") is True
    except (OSError,ValueError,http.client.HTTPException):
        return False
    finally:
        c.close()


def stop(p):
    if p.poll() is not None:
        return
    os.killpg(p.pid,signal.SIGTERM)
    try:
        p.wait(timeout=12)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL)
        p.wait(timeout=5)


os.umask(0o077)
WORK = STATE / "workspace"
WORK.mkdir(parents=True)
(WORK/"SOUL.md").write_text("You are a fictional test assistant. Reply briefly.\n")
ENV = {"PATH":"/usr/local/bin:/usr/bin:/bin","HOME":str(ROOT),"LANG":"C.UTF-8","TERM":"xterm-256color",
       "OPENCLAW_HOME":str(ROOT),"OPENCLAW_STATE_DIR":str(STATE),
       "OPENCLAW_CONFIG_PATH":str(STATE/"openclaw.json"),"OPENCLAW_WORKSPACE_DIR":str(WORK),
       "OPENCLAW_SKIP_CHANNELS":"1","OPENCLAW_DISABLE_BONJOUR":"1","NODE_DISABLE_COMPILE_CACHE":"1"}
for name in ("TMPDIR","XDG_CONFIG_HOME","XDG_STATE_HOME","XDG_DATA_HOME","XDG_RUNTIME_DIR","XDG_CACHE_HOME"):
    d=ROOT/name.lower()
    d.mkdir()
    ENV[name]=str(d)
config = {
 "gateway":{"mode":"local","bind":"loopback","port":18080,"auth":{"mode":"token","token":"fictional-gateway-token"}},
 "channels":{}, "plugins":{"enabled":False},
 "models":{"mode":"merge","providers":{"fictional":{"baseUrl":"http://127.0.0.1:18081/v1",
     "apiKey":"fictional-model-key","api":"openai-completions",
     "models":[{"id":"fixture","name":"Fixture","contextWindow":200000,"maxTokens":256}]}}},
 "agents":{"defaults":{"workspace":str(WORK),"model":{"primary":"fictional/fixture","fallbacks":[]}}},
 "tools":{"allow":["read"],"fs":{"workspaceOnly":True}},
 "logging":{"file":str(ROOT/"application.log")}}
(STATE/"openclaw.json").write_text(json.dumps(config))
gateway_log = ROOT / "gateway-output.log"
try:
    REPORT["stage"]="config-validation"
    result=call("config","validate","--json")
    if result.get("valid") is not True:
        raise RuntimeError("configuration rejected")
    REPORT["stage"]="gateway-start"
    mocklog=(ROOT/"model-output.log").open("w")
    mock=subprocess.Popen(["node","/opt/lab/mock.mjs"],stdout=mocklog,stderr=subprocess.STDOUT,
                          env=ENV,cwd=WORK,start_new_session=True)
    children.append(mock)
    log=gateway_log.open("w")
    gateway=subprocess.Popen(["node",CLI,"gateway","run"],stdout=log,stderr=subprocess.STDOUT,
                             env=ENV,cwd=WORK,start_new_session=True)
    children.append(gateway)
    deadline=time.monotonic()+300
    while not health():
        if gateway.poll() is not None:
            raise RuntimeError("Gateway exited "+str(gateway.returncode))
        if time.monotonic()>deadline:
            raise RuntimeError("health deadline")
        time.sleep(1)
    REPORT["health"]=True
    REPORT["stage"]="explicit-session-create"
    REPORT["create_calls"]=1
    created=call("gateway","call","sessions.create","--timeout","90000","--json","--params",
                 json.dumps({"agentId":"main","key":"tui-fictional-owner-test"}))
    if created.get("ok") is not True or not created.get("key") or created.get("runStarted") is not False:
        raise RuntimeError("unexpected session creation response")
    REPORT["created"]=True
    key=created["key"]
    REPORT["stage"]="chat-send"
    REPORT["send_calls"]=1
    sent=call("gateway","call","chat.send","--timeout","90000","--json","--params",
              json.dumps({"sessionKey":key,"message":"Reply with ORION-FICTIONAL-OK.",
                          "idempotencyKey":str(uuid.uuid4())}))
    REPORT["send_status"]=sent.get("status")
    REPORT["stage"]="history-read"
    deadline=time.monotonic()+90
    found=False
    while time.monotonic()<deadline:
        history=call("gateway","call","chat.history","--timeout","15000","--json",
                     "--params",json.dumps({"sessionKey":key,"limit":10}),seconds=25)
        for m in history.get("messages",[]):
            if m.get("role")=="assistant" and "ORION-FICTIONAL-OK" in json.dumps(m.get("content")):
                found=True
        if found:
            break
        raw=gateway_log.read_text(errors="replace")
        if '"event":"refusal"' in raw:
            break
        time.sleep(2)
    REPORT["assistant_marker_in_history"]=found
    REPORT["result"]="FICTIONAL_CONVERSATION_PASS" if found else "OWNER_FAILURE_OR_INCOMPLETE"
except Exception as e:
    REPORT["error_type"]=type(e).__name__
    REPORT["error"]=str(e).replace("fictional-gateway-token","[token]").replace("fictional-model-key","[key]")
finally:
    for p in reversed(children):
        stop(p)
    traces=[]
    raw=gateway_log.read_text(errors="replace") if gateway_log.exists() else ""
    for line in raw.splitlines():
        if line.startswith("ORION_OWNER_TRACE "):
            try:
                traces.append(json.loads(line.split(" ",1)[1]))
            except ValueError:
                pass
    REPORT["traces"]=traces
    REPORT["model_requests"]=len((ROOT/"model-count.txt").read_text().splitlines()) if (ROOT/"model-count.txt").exists() else 0
    dbfile=STATE/"agents/main/agent/openclaw-agent.sqlite"
    # Emit captured evidence before any optional post-run database inspection.
    print("ORION_DIAGNOSTIC_CAPTURE "+json.dumps(REPORT),flush=True)
    if dbfile.exists():
        try:
            probe = subprocess.run(["node","--no-warnings","--input-type=commonjs","-e",
                "const {DatabaseSync}=require('node:sqlite');"
                "const db=new DatabaseSync(process.argv[1],{readOnly:true});"
                "try{console.log(JSON.stringify({integrity:db.prepare('PRAGMA integrity_check').get(),"
                "sessions:db.prepare('SELECT count(*) AS n FROM session_nodes').get().n}))}"
                "finally{db.close()}", str(dbfile)], env=ENV, capture_output=True,text=True,timeout=30)
            if probe.returncode:
                REPORT["inspection_error"]="Node SQLite inspection exited "+str(probe.returncode)
            else:
                REPORT["database_inspection"]=json.loads(probe.stdout)
        except (ValueError,OSError,subprocess.SubprocessError) as e:
            REPORT["inspection_error"]=type(e).__name__
    if REPORT["result"]=="STOP" or REPORT["result"]=="OWNER_FAILURE_OR_INCOMPLETE":
        REPORT["log_tail"]=raw[-6000:].replace("fictional-gateway-token","[token]").replace("fictional-model-key","[key]")
    print("ORION_DIAGNOSTIC_RESULT "+json.dumps(REPORT),flush=True)
    if REPORT["result"]!="FICTIONAL_CONVERSATION_PASS" and not any(t.get("event")=="refusal" for t in traces):
        raise SystemExit(1)
