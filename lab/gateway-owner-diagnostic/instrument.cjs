const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const dist='/opt/beta/node_modules/openclaw/dist', edits=[];
function change(s,old,next,label) {
 if(s.split(old).length!==2) throw Error('anchor mismatch: '+label);
 return s.replace(old,next);
}
function trace(value) {
 return 'try { process.stderr.write("ORION_OWNER_TRACE "+JSON.stringify('+value+')+"\\n"); } catch {}\n';
}
function visit(dir) {
 for(const e of fs.readdirSync(dir,{withFileTypes:true})) {
  const file=path.join(dir,e.name);
  if(e.isDirectory()) {if(e.name!=='node_modules')visit(file);continue;}
  if(!e.isFile()||!e.name.endsWith('.mjs')&&!e.name.endsWith('.js'))continue;
  let source=fs.readFileSync(file,'utf8'),original=source,kinds=[];
  if(source.includes('function captureSessionStoreReadTarget(')) {
   let start=source.indexOf('function captureSessionStoreReadTarget('),end=source.indexOf('\n}',start)+2;
   if(end<start)throw Error('function end missing');
   let s=source.slice(start,end);
   const records=[
    ['const identities = captureSessionStoreCandidateIdentities(candidates);',
     'const identities = captureSessionStoreCandidateIdentities(candidates);\n'+trace('{event:"capture",message:changedMessage,storePath,logicalPath:logical.path??null,prepared:!!prepared,canonical:prepared?.canonicalPath??null,candidates:candidates.map(c=>({path:c.path,physical:c.physicalPath,scope:c.scope??null})),identityPaths:[...identities.keys()]}'),'capture'],
    ['if (!identity) {','if (!identity) {\n'+trace('{event:"refusal",branch:"missing-candidate-identity",message:changedMessage,captured:storePath,resolved:options.path,prepared:!!prepared}'),'missing'],
    ['if (options.path !== prepared.canonicalPath) {','if (options.path !== prepared.canonicalPath) {\n'+trace('{event:"refusal",branch:"prepared-path-differs",message:changedMessage,captured:storePath,canonical:prepared.canonicalPath,resolved:options.path}'),'prepared'],
    ['const identity = prepared',''+trace('{event:"resolved",message:changedMessage,captured:storePath,resolved:options.path,samePath:storePath===options.path,prepared:!!prepared,agent:options.agentId}')+'const identity = prepared','resolved']
   ];
   for(const [a,b,label] of records)s=change(s,a,b,label);
   if((s.match(/throw new Error\(changedMessage\)/g)||[]).length!==2)throw Error('guard altered');
   source=source.slice(0,start)+s+source.slice(end); kinds.push('guard');
  }
  if(source.includes('async function prepareSqliteTranscriptReadScope(')) {
   let start=source.indexOf('async function prepareSqliteTranscriptReadScope('),end=source.indexOf('\n}',start)+2;
   let s=source.slice(start,end);
   s=change(s,'const reader = getOwnedSessionTranscriptReader(readScope);',
    'const reader = getOwnedSessionTranscriptReader(readScope);\n'+trace('{event:"active-reader",selected:!!reader,inputStore:readScope.storePath??null,inputAgent:readScope.agentId??null,readerPath:reader?.database.path??null,readerAgent:reader?.database.agentId??null}'),'reader');
   source=source.slice(0,start)+s+source.slice(end);kinds.push('reader');
  }
  if(source!==original) {
   fs.writeFileSync(file,source);
   require('node:child_process').execFileSync(process.execPath,['--check',file],{stdio:'pipe'});
   edits.push({file:path.relative(dist,file),kinds,before:crypto.createHash('sha256').update(original).digest('hex'),after:crypto.createHash('sha256').update(source).digest('hex')});
  }
 }
}
visit(dist);
if(!edits.some(e=>e.kinds.includes('guard'))||!edits.some(e=>e.kinds.includes('reader')))throw Error('instrumentation incomplete');
fs.writeFileSync('/opt/lab/instrumentation.json',JSON.stringify(edits,null,2));
console.log('INSTRUMENTED '+JSON.stringify(edits));
