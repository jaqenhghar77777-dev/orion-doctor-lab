"""Offline regressions. No real provider requests or Orion state are used."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

import openrouter_reply_v1 as helper
import orion_chat_v2 as chat

USER = "The user prefers concise updates during implementation work."
MEMORY = "We built a fictional orchard sensor with three green lights."
NOTE = "# Recovery\n\n## Excerpt 1\n\nSource example.md, lines 1 to 4\n\n"+MEMORY+"\n"


def records(workspace, user=USER, memory=NOTE, nonce="fictional-proof", error=False, result=True):
    data=[]
    for i,(name,content) in enumerate((("USER.md",user),(chat.NOTE,memory),("read-proof.txt",nonce))):
        data.append({"message":{"role":"assistant","content":[{"type":"toolCall","id":str(i),"name":"read","arguments":{"path":str(workspace / name)}}]}})
        if result:
            data.append({"message":{"role":"toolResult","toolCallId":str(i),"toolName":"read","isError":error,
                                    "content":[{"type":"text","text":"Error: EACCES" if error else content}]}})
    return data


def answer(nonce="fictional-proof"):
    return json.dumps({"user_fact":USER,"user_quote":USER,"memory_fact":MEMORY,"memory_quote":MEMORY,"proof":nonce})


class Checks(unittest.TestCase):
    def test_quotes_and_actual_read_results_are_required(self):
        w=Path("/fiction")
        evidence=chat.tool_evidence(records(w),w)
        self.assertTrue(all(chat.verify_reply(answer(),evidence,USER,NOTE,"fictional-proof").values()))
        self.assertFalse(all(chat.verify_reply(answer(),[],USER,NOTE,"fictional-proof").values()))
        # Quotes present in source alone cannot substitute for successful tool output.
        evidence=chat.tool_evidence(records(w,user="Wrong file",memory="Wrong file"),w)
        self.assertFalse(all(chat.verify_reply(answer(),evidence,USER,NOTE,"fictional-proof").values()))

    def test_errors_and_missing_results_fail(self):
        w=Path("/fiction")
        for kwargs in ({"error":True},{"result":False}):
            evidence=chat.tool_evidence(records(w,**kwargs),w)
            self.assertFalse(all(chat.verify_reply(answer(),evidence,USER,NOTE,"fictional-proof").values()))
            self.assertTrue(all(x["status"]!="SUCCESS" for x in evidence))
        self.assertEqual(chat.tool_evidence(records(w,error=True),w)[0]["error"],"EACCES")

    def test_guessed_fact_or_nonce_fails(self):
        w=Path("/fiction");e=chat.tool_evidence(records(w),w)
        a=json.loads(answer());a["user_fact"]="Unsupported claim"
        self.assertFalse(all(chat.verify_reply(json.dumps(a),e,USER,NOTE,"fictional-proof").values()))
        self.assertFalse(all(chat.verify_reply(answer("guessed"),e,USER,NOTE,"fictional-proof").values()))
        self.assertFalse(all(chat.verify_reply("[]",e,USER,NOTE,"fictional-proof").values()))

    def test_metadata_contains_no_contents(self):
        w=Path("/fiction");e=chat.public_evidence(chat.tool_evidence(records(w),w))
        self.assertNotIn(USER,json.dumps(e))
        self.assertNotIn("fictional-proof",json.dumps(e))
        self.assertNotIn(str(w),json.dumps(e))

    def test_multiline_waits_for_send(self):
        consumed=[];lines=iter(["  first", "", "second", "/send"])
        def read():
            value=next(lines);consumed.append(value)
            return value
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(chat.collect_message(read),"  first\n\nsecond")
        self.assertEqual(consumed,["  first","","second","/send"])

    def test_cancel_quit_and_eof_never_submit(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for values,expected in ((["unused","/cancel"],""),(["unused","/quit"],None)):
                lines=iter(values)
                self.assertEqual(chat.collect_message(lambda:next(lines)),expected)
            self.assertIsNone(chat.collect_message(lambda:(_ for _ in ()).throw(EOFError())))

    def test_isolated_verification_installs_only_after_success(self):
        for mode in ("success","tool-error","guessed"):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);old=root/"chat";w=old/"home/.openclaw/workspace";w.mkdir(parents=True)
                docs={n:("identity "+n) for n in helper.HASHES}
                docs["USER.md"]=USER;docs[chat.NOTE]=NOTE
                for name,value in docs.items():
                    file=w/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(value)
                hashes={n:hashlib.sha256(value.encode()).hexdigest() for n,value in docs.items()}
                # A real SQLite fixture supplies the read-only existing-session audit.
                db=w.parent/"agents/main/agent/openclaw-agent.sqlite";db.parent.mkdir(parents=True)
                conn=sqlite3.connect(db)
                conn.execute("create table transcript_events(session_id,seq,event_json,event_zstd)")
                old_session=str(uuid.uuid4())
                for i,event in enumerate(records(w,error=True)):
                    conn.execute("insert into transcript_events values(?,?,?,null)",(old_session,i,json.dumps(event)))
                conn.commit();conn.close()
                receipt={"session_id":old_session,"config":{"gateway":{"mode":"local","port":32123,"auth":{"token":"old-token"}},
                    "agents":{"defaults":{"workspace":str(w),"model":{"primary":chat.MODEL,"fallbacks":[]}}},
                    "plugins":{"enabled":True,"allow":["openrouter"]},"tools":{"allow":["read"],"fs":{"workspaceOnly":True}}}}
                (old/"chat-session.json").write_text(json.dumps(receipt))
                before={p:p.read_bytes() for p in old.rglob("*") if p.is_file()}
                calls=[]
                def call(env,workspace,seconds,*args):
                    calls.append(args)
                    self.assertNotEqual(workspace,w)
                    self.assertEqual(env["OPENCLAW_WORKSPACE_DIR"],str(workspace))
                    if args[0]=="config":
                        self.assertNotIn("OPENROUTER_API_KEY",env)
                        return subprocess.CompletedProcess(args,0,json.dumps({"valid":True,"path":env["OPENCLAW_CONFIG_PATH"]}),"")
                    self.assertEqual(env["OPENROUTER_API_KEY"],"fixture-key")
                    self.assertIn(chat.NOTE,(workspace/"MEMORY.md").read_text())
                    self.assertNotIn("old-token",Path(env["OPENCLAW_CONFIG_PATH"]).read_text())
                    session=args[args.index("--session-id")+1]
                    nonce=(workspace/"read-proof.txt").read_text().strip()
                    proof=records(workspace,nonce=nonce,error=mode=="tool-error")
                    newdb=workspace.parent/"agents/main/agent/openclaw-agent.sqlite"
                    newdb.parent.mkdir(parents=True)
                    c=sqlite3.connect(newdb);c.execute("create table transcript_events(session_id,seq,event_json,event_zstd)")
                    for i,event in enumerate(proof):
                        c.execute("insert into transcript_events values(?,?,?,null)",(session,i,json.dumps(event)))
                    c.commit();c.close()
                    text=answer("guess" if mode=="guessed" else nonce)
                    return subprocess.CompletedProcess(args,0,json.dumps({"payloads":[{"text":text}]}),"")
                with patch.object(chat,"CHAT",old),patch.object(helper,"HASHES",hashes),patch.object(chat,"HASHES",hashes),patch.object(chat,"call",side_effect=call),patch("getpass.getpass",return_value="fixture-key"),contextlib.redirect_stdout(io.StringIO()) as out:
                    rc=chat.verify(w,receipt)
                    self.assertEqual(rc,0 if mode=="success" else 1)
                    self.assertEqual(len(calls),2)  # Exactly one validation and one model turn.
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
                self.assertNotIn("fixture-key",out.getvalue())
                self.assertEqual((old/"orion_chat_v2.py").exists(),mode=="success")
                self.assertEqual((w/"MEMORY.md").exists(),mode=="success")
                self.assertEqual((old/"read-verification-v2.json").exists(),mode=="success")

    def test_line_wrap_equivalence_preserves_words_and_punctuation(self):
        w=Path("/fiction")
        wrapped=NOTE.replace("fictional orchard","fictional\norchard")
        e=chat.tool_evidence(records(w,memory=wrapped),w)
        self.assertTrue(all(chat.verify_reply(answer(),e,USER,wrapped,"fictional-proof").values()))
        changed=json.loads(answer());changed["memory_quote"]=MEMORY.replace("three","four")
        changed["memory_fact"]=changed["memory_quote"]
        self.assertFalse(all(chat.verify_reply(json.dumps(changed),e,USER,wrapped,"fictional-proof").values()))

    def test_saved_result_finalization_uses_no_model_and_preserves_original_report(self):
        import finalize_read_v2 as finalizer
        for variant in ("line-wrap","unsupported-quote"):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);old=root/"chat";source=old/"home/.openclaw/workspace"
                test=root/"test";target=test/"home/.openclaw/workspace"
                docs={n:"identity "+n for n in helper.HASHES}
                docs["USER.md"]=USER;docs[chat.NOTE]=NOTE.replace("fictional orchard","fictional\norchard")
                for workspace in (source,target):
                    for name,value in docs.items():
                        file=workspace/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(value)
                hashes={n:hashlib.sha256(value.encode()).hexdigest() for n,value in docs.items()}
                (target/"read-proof.txt").write_text("fictional-proof\n")
                original=json.dumps({"result":"READ_VERIFY_STOP","exit":0,"test_directory":str(test)}).encode()
                (test/"verification-report.json").write_bytes(original)
                saved=json.loads(answer())
                if variant=="unsupported-quote":
                    saved["memory_fact"]=saved["memory_quote"]="A completely unsupported memory claim."
                (test/"reply.txt").write_text(json.dumps(saved))
                db=target.parent/"agents/main/agent/openclaw-agent.sqlite";db.parent.mkdir(parents=True)
                c=sqlite3.connect(db);c.execute("create table transcript_events(session_id,seq,event_json,event_zstd)")
                for i,event in enumerate(records(target,memory=docs[chat.NOTE])):
                    c.execute("insert into transcript_events values('only-session',?,?,null)",(i,json.dumps(event)))
                c.commit();c.close()
                with patch.object(chat,"CHAT",old),patch.object(helper,"HASHES",hashes),patch.object(chat,"HASHES",hashes),patch.object(chat,"call",side_effect=AssertionError("no inference")),contextlib.redirect_stdout(io.StringIO()) as out:
                    rc=finalizer.finalize(test)
                self.assertEqual(rc,0 if variant=="line-wrap" else 1)
                report=json.loads(out.getvalue())
                self.assertEqual(report["model_requests"],0)
                self.assertEqual((test/"verification-report.json").read_bytes(),original)
                self.assertEqual((old/"orion_chat_v2.py").exists(),variant=="line-wrap")

    def test_chat_submits_one_multiline_turn_and_keeps_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);w=root/"home/.openclaw/workspace";w.mkdir(parents=True)
            session=str(uuid.uuid4());calls=[]
            def call(env,workspace,seconds,*args):
                calls.append(args)
                self.assertEqual(workspace,w)
                self.assertEqual(args[args.index("--session-id")+1],session)
                self.assertEqual(args[args.index("--message")+1],chat.GUIDANCE+"one\n\ntwo")
                return subprocess.CompletedProcess(args,0,json.dumps({"payloads":[{"text":"fixture reply"}]}),"")
            with patch.object(chat,"CHAT",root),patch.object(chat,"checked_workspace"),patch.object(chat,"call",side_effect=call),patch.object(chat,"collect_message",side_effect=["one\n\ntwo","",None]),patch("getpass.getpass",return_value="fixture-key"),contextlib.redirect_stdout(io.StringIO()):
                chat.chat(w,{"session_id":session})
            self.assertEqual(len(calls),1)


if __name__=="__main__":
    unittest.main()
