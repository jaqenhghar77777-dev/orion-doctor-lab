import fs from 'node:fs';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {logicalEvent} from './compat.mjs';
import {getSessionEntry} from '/opt/beta/node_modules/openclaw/dist/plugin-sdk/session-store-runtime.js';
import {readSessionTranscriptEvents} from '/opt/beta/node_modules/openclaw/dist/plugin-sdk/session-transcript-runtime.js';

const [listingFile, reportFile] = process.argv.slice(2);
const state = process.env.OPENCLAW_STATE_DIR;
const source = new DatabaseSync('/input/agents/main/agent/openclaw-agent.sqlite', {readOnly:true});
const report = {result:'STOP', other_histories_checked:0, other_histories_failed:0};
let stage = 'SOURCE_CURRENT_SESSION';
function messageText(event) {
  const message = event?.message;
  if (!['user','assistant'].includes(message?.role)) return null;
  const text = typeof message.content === 'string' ? message.content :
    (Array.isArray(message.content) ? message.content.filter(p=>p?.type==='text').map(p=>p.text).join('') : '');
  return text.trim() ? JSON.stringify([message.role,text]) : null;
}
try {
  const nodes = source.prepare(`SELECT session_key, current_session_id FROM session_nodes
    WHERE entry_valid=1 AND current_session_id IS NOT NULL ORDER BY updated_at DESC,session_key`).all();
  const events = source.prepare('SELECT event_json,event_zstd FROM transcript_events WHERE session_id=? ORDER BY seq');
  const keys = source.prepare('SELECT main_key FROM session_key_contract').get();
  const preferred = new Set(['agent:main:main', keys?.main_key, 'agent:main:'+keys?.main_key]);
  // Prefer the default chat when populated, then the most recent original current chat with messages.
  nodes.sort((a,b)=>Number(preferred.has(b.session_key))-Number(preferred.has(a.session_key)));
  const listing = JSON.parse(fs.readFileSync(listingFile)).sessions;
  const storePath = path.join(state,'agents/main/sessions/sessions.json');
  let selected;
  for (const node of nodes) {
    const original = events.all(node.current_session_id).map(logicalEvent).map(messageText).filter(Boolean);
    if (!original.length) continue;
    selected = node;
    stage = 'MAIN_SESSION_LISTING';
    if (!listing.some(r=>r.key===node.session_key && r.sessionId===node.current_session_id)) throw Error(stage);
    const scope = {agentId:'main',storePath,sessionKey:node.session_key,sessionId:node.current_session_id};
    stage = 'SDK_CURRENT_SESSION_IDENTITY';
    if ((await getSessionEntry(scope))?.sessionId!==scope.sessionId) throw Error(stage);
    stage = 'SDK_CURRENT_MESSAGE_READ';
    const returned = (await readSessionTranscriptEvents(scope)).map(messageText).filter(Boolean);
    const originals = new Set(original);
    if (!returned.length || !returned.every(m=>originals.has(m))) throw Error(stage);
    report.original_messages_read = returned.length;
    report.default_session_key = preferred.has(node.session_key);
    break;
  }
  if (!selected) throw Error(stage);
  stage = 'SDK_HISTORY_ENUMERATION';
  for (const row of source.prepare(`SELECT DISTINCT w.session_key,w.session_id FROM session_windows w
    JOIN transcript_events e ON e.session_id=w.session_id`).all()) {
    if (row.session_id===selected.current_session_id && row.session_key===selected.session_key) continue;
    report.other_histories_checked++;
    try {
      const read = await readSessionTranscriptEvents({agentId:'main',storePath,sessionKey:row.session_key,sessionId:row.session_id});
      if (!Array.isArray(read) || !read.length) report.other_histories_failed++;
    } catch {report.other_histories_failed++;}
  }
  report.result = 'PASS';
} catch (error) {
  report.operation = stage;
  report.failure_code = error.message === stage ? stage : 'SDK_OR_DATABASE_EXCEPTION';
  process.exitCode = 1;
} finally {
  source.close();
  fs.writeFileSync(reportFile,JSON.stringify(report));
}
