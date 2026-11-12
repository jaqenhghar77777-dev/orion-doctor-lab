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

    def test_source_ranges_handle_headers_boundaries_and_metadata(self):
        import base64
        from finalize_read_v3 import reconstruct
        rows=[["old.md",1,2,base64.b64encode(MEMORY.encode()).decode()],
              ["new.md",1,2,base64.b64encode(b"The second real excerpt describes seven violet lanterns.").decode()]]
        note,spans=reconstruct(rows)
        for quote,origin in [
            (MEMORY,"body_only"),
            ("Source \"old.md\", lines 1 to 2\n\n"+MEMORY,"body_plus_header"),
            (note[spans[0][0]:spans[1][1]].decode(),"cross_excerpt")]:
            result=chat.memory_quote_origin(quote,note,spans)
            self.assertTrue(result["grounded"]);self.assertEqual(result["origin"],origin)
        for quote in ("Historical excerpts from the reviewed local backup.",'Source "old.md", lines 1 to 2'):
            self.assertFalse(chat.memory_quote_origin(quote,note,spans)["grounded"])
        e=chat.tool_evidence(records(Path("/fiction"),memory=note.decode(),error=True),Path("/fiction"))
        self.assertFalse(chat.verify_reply(answer(),e,USER,note.decode(),"fictional-proof",memory_spans=spans)["memory_excerpt_quote"])

    def test_final_source_range_recheck_preserves_reports_and_uses_no_model(self):
        import base64
        import tarfile
        import finalize_read_v3 as finalizer
        for metadata_only in (False,True):
            with self.subTest(metadata_only=metadata_only),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);old=root/"chat";source=old/"home/.openclaw/workspace"
                test=root/"test";target=test/"home/.openclaw/workspace"
                rows=[["fact.md",i,i+1,base64.b64encode(MEMORY.encode()).decode()] for i in range(70)]
                note,spans=finalizer.reconstruct(rows)
                docs={n:("identity "+n).encode() for n in helper.HASHES}
                docs["USER.md"]=USER.encode();docs[chat.NOTE]=note
                for workspace in (source,target):
                    for name,body in docs.items():
                        f=workspace/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(body)
                hashes={n:hashlib.sha256(b).hexdigest() for n,b in docs.items()}
                (target/"read-proof.txt").write_text("fictional-proof")
                originals={"verification-report.json":json.dumps({"result":"READ_VERIFY_STOP","test_directory":str(test),"exit":0}).encode(),
                           "quote-verification-v2.json":b'{"result":"READ_VERIFY_STOP"}'}
                for name,body in originals.items():(test/name).write_bytes(body)
                quote="Historical excerpts from the reviewed local backup." if metadata_only else 'Source "fact.md", lines 0 to 1\n\n'+MEMORY
                saved=json.loads(answer());saved["memory_fact"]=saved["memory_quote"]=quote
                (test/"reply.txt").write_text(json.dumps(saved))
                datafile=root/"archive.sqlite"
                c=sqlite3.connect(datafile);c.execute("create table memory_index_chunks(chunk_rowid integer primary key,id,path,start_line,end_line,text)")
                for i in range(70):c.execute("insert into memory_index_chunks values(?,?,?,?,?,?)",(i,str(i),"fact.md",i,i+1,MEMORY))
                c.commit();c.close()
                database=datafile.read_bytes();manifest=json.dumps({"files":[{"path":finalizer.MAIN,"sha256":hashlib.sha256(database).hexdigest()}]}).encode()
                archive=root/"reviewed.tgz"
                with tarfile.open(archive,"w:gz") as tar:
                    for name,body in (("manifest.json",manifest),(finalizer.MAIN,database)):
                        info=tarfile.TarInfo(name);info.size=len(body);tar.addfile(info,io.BytesIO(body))
                audit=target.parent/"agents/main/agent/openclaw-agent.sqlite";audit.parent.mkdir(parents=True)
                c=sqlite3.connect(audit);c.execute("create table transcript_events(session_id,seq,event_json,event_zstd)")
                for i,event in enumerate(records(target,memory=note.decode())):
                    c.execute("insert into transcript_events values('only-session',?,?,null)",(i,json.dumps(event)))
                c.commit();c.close()
                before={f:f.read_bytes() for f in old.rglob("*") if f.is_file()}
                with patch.object(chat,"CHAT",old),patch.object(helper,"HASHES",hashes),patch.object(chat,"HASHES",hashes),patch.object(chat,"call",side_effect=AssertionError("no model request")),patch.object(finalizer,"ARCHIVE",archive),patch.object(finalizer,"ARCHIVE_HASH",hashlib.sha256(archive.read_bytes()).hexdigest()),patch.object(finalizer,"MANIFEST_HASH",hashlib.sha256(manifest).hexdigest()),contextlib.redirect_stdout(io.StringIO()) as output:
                    rc=finalizer.finalize(test)
                self.assertEqual(rc,1 if metadata_only else 0)
                report=json.loads(output.getvalue())
                self.assertEqual(report["model_requests"],0)
                self.assertEqual(report["source_chunks_verified"],70)
                self.assertEqual(report["quote_origin"]["origin"],"metadata_only" if metadata_only else "body_plus_header")
                self.assertTrue(all(f.read_bytes()==b for f,b in before.items()))
                self.assertTrue(all((test/n).read_bytes()==b for n,b in originals.items()))
                self.assertEqual((old/"orion_chat_v2.py").exists(),not metadata_only)

    def test_targeted_body_turn_reuses_old_proof_but_requires_new_memory_read(self):
        import verify_memory_body_v1 as targeted
        import finalize_read_v3 as saved
        import base64
        for mode in ("success","metadata","no-new-read"):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);old=root/"chat";source=old/"home/.openclaw/workspace"
                test=root/"old-test";target=test/"home/.openclaw/workspace"
                note,spans=saved.reconstruct([["fact.md",1,2,base64.b64encode(MEMORY.encode()).decode()]])
                docs={n:("identity "+n).encode() for n in helper.HASHES}
                docs["USER.md"]=USER.encode();docs[chat.NOTE]=note
                for workspace in (source,target):
                    for name,body in docs.items():
                        file=workspace/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(body)
                hashes={n:hashlib.sha256(b).hexdigest() for n,b in docs.items()}
                (target/"read-proof.txt").write_text("fictional-proof")
                originals={"verification-report.json":json.dumps({"exit":0}).encode(),
                           "quote-verification-v2.json":b'{"result":"READ_VERIFY_STOP"}',
                           "source-range-verification-v3.json":b'{"result":"READ_VERIFY_STOP","quote_origin":{"origin":"metadata_only"}}'}
                for name,body in originals.items():(test/name).write_bytes(body)
                old_answer=json.loads(answer());old_answer["memory_fact"]=old_answer["memory_quote"]="Historical excerpts from the reviewed local backup."
                (test/"reply.txt").write_text(json.dumps(old_answer))
                (old/"chat-session.json").write_text(json.dumps({"config":{"gateway":{"mode":"local","auth":{"token":"old-key"}},"agents":{"defaults":{"workspace":str(source)}}}}))
                (old/"old-history.bin").write_bytes(b"saved-session-preserved")
                def write_events(state,session,events):
                    db=state/"agents/main/agent/openclaw-agent.sqlite";db.parent.mkdir(parents=True,exist_ok=True)
                    c=sqlite3.connect(db);c.execute("create table transcript_events(session_id,seq,event_json,event_zstd)")
                    for i,e in enumerate(events):c.execute("insert into transcript_events values(?,?,?,null)",(session,i,json.dumps(e)))
                    c.commit();c.close()
                write_events(target.parent,"old-session",records(target,memory=note.decode()))
                before={f:f.read_bytes() for f in old.rglob("*") if f.is_file()}
                turns=[]
                def call(env,workspace,seconds,*args):
                    if args[0]=="config":
                        return subprocess.CompletedProcess(args,0,json.dumps({"valid":True}),"")
                    turns.append(args);prompt=args[args.index("--message")+1]
                    self.assertNotIn(MEMORY,prompt)
                    expected_offset,_=targeted.body_line(note,spans)
                    self.assertIn("offset="+str(expected_offset),prompt)
                    session=args[args.index("--session-id")+1]
                    new_records=[] if mode=="no-new-read" else records(workspace,memory=note.decode())[2:4]
                    write_events(workspace.parent,session,new_records)
                    quote="Historical excerpts from the reviewed local backup." if mode=="metadata" else MEMORY
                    return subprocess.CompletedProcess(args,0,json.dumps({"payloads":[{"text":json.dumps({"memory_fact":quote,"memory_quote":quote})}]}),"")
                with patch.object(chat,"CHAT",old),patch.object(chat,"HASHES",hashes),patch.object(helper,"HASHES",hashes),patch.object(saved,"source_spans",return_value=spans),patch.object(chat,"call",side_effect=call),patch("getpass.getpass",return_value="fixture-key"),contextlib.redirect_stdout(io.StringIO()):
                    rc=targeted.verify(test)
                    self.assertEqual(rc,0 if mode=="success" else 1)
                    with self.assertRaisesRegex(ValueError,"already attempted"):targeted.verify(test)
                self.assertEqual(len(turns),1)
                self.assertTrue(all(f.read_bytes()==body for f,body in before.items()))
                self.assertTrue(all((test/n).read_bytes()==body for n,body in originals.items()))
                self.assertEqual((old/"orion_chat_v2.py").exists(),mode=="success")

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
