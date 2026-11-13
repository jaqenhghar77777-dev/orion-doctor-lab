const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const dist = process.argv[2] || '/opt/beta/node_modules/openclaw/dist';
const modules = [
  ['session-accessor--Bmf8-N6.mjs','01ae682ed9af10a21aea941fc29dbc2762f4dd86c000c60a9ae0b3e3c50abe83','guard'],
  ['session-accessor.sqlite-read-scope-yZ5VOObI.mjs','e33b632bab3a4ccd58246a33061179c29edfe03c004aa85c859bdf1c8d13801d','reader'],
  ['config/sessions/transcript-session-accessor.sqlite-read-scope-BBOz-FqW.mjs','6f5ed4dfb781f40f960b106efc68d37d667be55fa84603142e88ed025af71b04','reader'],
  ['chat-send-handler-QjdhYIde.mjs','d2b0646259ffdf6a6b47b39a1f8514073d975ee376cf55794f2c9d5941c0732c','rpc']
];
const prelude = `
import * as orionFS from 'node:fs';
function orionPhysical(p) {
  if (!p) return null;
  try {
    const st=orionFS.statSync(p,{bigint:true});
    return {canonical:orionFS.realpathSync.native(p),fileKey:'file:'+st.dev+':'+st.ino};
  } catch (e) { return {error:e.code || 'unavailable'}; }
}
function orionEmit(event, fields) {
  try {
    const row = {event, tick:process.hrtime.bigint().toString(), ...fields};
    orionFS.appendFileSync('/home/replay/trace.jsonl',JSON.stringify(row)+'\\n');
  } catch {}
}
`;
for (const [file, expected, kind] of modules) {
  const name = path.join(dist,file);
  const original = fs.readFileSync(name,'utf8');
  if (crypto.createHash('sha256').update(original).digest('hex') !== expected) throw Error('Unexpected pinned input: '+file);
  const edits = [];
  function after(anchor, observation) {
    if (original.split(anchor).length !== 2) throw Error('Nonunique original anchor '+anchor);
    edits.push([anchor, anchor+'\n'+observation]);
  }
  if (kind === 'guard') {
    const a='const identities = captureSessionStoreCandidateIdentities(candidates);\n\treturn { resolve(resolved) {';
    edits.push([a, a.replace('\n\treturn', `\nconst orionId = process.hrtime.bigint().toString();
orionEmit('capture',{id:orionId,message:changedMessage,input:scope.storePath??null,storePath,agent:toDatabaseOptions(logical).agentId,observed:orionPhysical(storePath),prepared:prepared?{canonical:prepared.canonicalPath,agent:prepared.validation.agentId,key:prepared.validation.identity,birthtime:prepared.validation.birthtime}:null,candidates:candidates.map(c=>({path:c.path,physical:c.physicalPath,scope:c.scope??null})),identities:[...identities]});
\treturn`)]);
    const a2='const identity = prepared ? {\n\t\t\tkey: `file:${prepared.validation.identity}`,';
    edits.push([a2,`orionEmit('resolved',{id:orionId,message:changedMessage,path:options.path,agent:options.agentId,observed:orionPhysical(options.path)});\n`+a2]);
    for (const [condition,branch] of [['!identity','missing-candidate-identity'],['options.path !== prepared.canonicalPath','prepared-path-differs']]) {
      const before='if ('+condition+') throw new Error(changedMessage);';
      edits.push([before,'if ('+condition+') { orionEmit("refusal",{id:orionId,message:changedMessage,branch:"'+branch+'",stack:new Error().stack?.split("\\n").slice(2,10)}); throw new Error(changedMessage); }']);
    }
  } else if (kind === 'reader') {
    after('const reader = getOwnedSessionTranscriptReader(readScope);',
      `orionEmit('reader',{selected:!!reader,input:readScope.storePath??null,agent:readScope.agentId??null,path:reader?.database.path??null,dbAgent:reader?.database.agentId??null,caller:new Error().stack?.split('\\n').slice(2,5)});`);
  } else {
    after('async function handleChatSend(options, onAdmissionOwned, externalAuthorityAdmission) {',
      "orionEmit('chat-send',{});");
  }
  let source = original;
  for (const [a,b] of edits) {
    if (source.split(a).length !== 2) throw Error('Bad anchor '+a);
    source=source.replace(a,()=>b);
  }
  let inverse=source;
  for (const [a,b] of [...edits].reverse()) inverse=inverse.replace(b,()=>a);
  if(inverse!==original) throw Error('Instrumentation did not round-trip');
  fs.writeFileSync(name,prelude+source);
  execFileSync(process.execPath,['--check',name]);
  console.log('PIN_AND_REVERSIBLE_TRACE_OK '+file);
}
