"""Check a complete same-send live-input handoff in a fresh one-message container."""
LIVE = "Live input changed its captured database owner"
CASES = ("control","no-reader","prepared","alias","other-file","revoked","late-sibling","stable-handoff")


def check_case(case, report, trace):
    assert case in CASES
    assert report.get("created") and report["create_calls"] == report["send_calls"] == 1
    assert report.get("database_inspection",{}).get("integrity") == {"integrity_check":"ok"}
    def unique(event, pred=lambda r: True):
        matches = [(i,r) for i,r in enumerate(trace) if r["event"] == event and pred(r)]
        assert len(matches)==1, (event,len(matches))
        return matches[0]
    send,_ = unique("chat-send")
    cap,c = unique("capture",lambda r:r["message"]==LIVE)
    reader,rd = unique("reader",lambda r:any("prepareForeignLiveSessionPendingInputEntries" in line for line in r["caller"]))
    hand,h = unique("handoff",lambda r:r["mode"]==case)
    same = lambda r:r.get("id")==c["id"]
    resolve,z = unique("resolved",same)
    assert send < cap < reader < hand < resolve
    submit,sub = unique("capture",lambda r:r["message"]=="Submitted input changed its captured database owner")
    sr,_ = unique("resolved",lambda r:r["id"]==sub["id"])
    assert send < submit < sr < cap
    assert c["sessionKey"] == rd["sessionKey"] == h["sessionKey"]
    assert c["sessionId"] == rd["sessionId"] == h["sessionId"]
    assert rd["selected"] == (case!="no-reader")
    assert h["supplied"]==z["path"]
    if rd["selected"]:
        assert rd["path"]==h["original"] and rd["dbAgent"]==z["agent"]
    has_receipt = case not in ("control","no-reader","late-sibling")
    assert bool(c["prepared"])==has_receipt
    key=z["observed"]["fileKey"]
    if has_receipt:
        original="file:"+c["prepared"]["key"]
        assert h["prior"]["fileKey"]==original
        assert (original==key)==(case!="other-file")
    if case in ("control","no-reader"):
        assert key in [val["key"] for _,val in c["identities"]]
    if case=="late-sibling":
        assert key not in [val["key"] for _,val in c["identities"]]
        assert h["prior"]["fileKey"]!=key and any(x["scope"]=="sibling-family" for x in c["candidates"])
    passed = case in ("control","no-reader","prepared","stable-handoff")
    assert bool(report.get("assistant_marker_in_history"))==passed and report["model_requests"]==int(passed)
    errors=[r for r in trace if r["event"] in ("refusal","receipt-rejected")]
    if not passed:
        assert len(errors)>=1 and same(errors[0])
        if case=="revoked":
            assert errors[0]["event"]=="receipt-rejected" and errors[0]["reason"]=="Session reader validation is no longer current"
        else:
            assert errors[0]["branch"]==("missing-candidate-identity" if case=="late-sibling" else "prepared-path-differs")
    else:
        assert not errors
    current=[i for i,r in enumerate(trace) if r["event"]=="receipt-current" and same(r)]
    assert bool(current)==(has_receipt and case!="revoked")
    if case in ("alias","other-file"):
        throw,_=unique("refusal",same)
        assert resolve < current[0] < throw and h["original"]!=h["supplied"]
