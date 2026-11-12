// Local candidate preparation only. Imports built-in modules and has no network operation.
import fs from 'node:fs';
import path from 'node:path';
import {createHash,createHmac,randomBytes} from 'node:crypto';
import {DatabaseSync,backup} from 'node:sqlite';
import {zstdCompressSync,zstdDecompressSync} from 'node:zlib';

const RESTORE='/root/orion-real-rehearsal-9a_4zlyq';
const ARCHIVE_HASH='daccf87f3dc4173d7ee52e300d33546e82d73d2cdf279a69c57f8f22df06707c';
const MARKER='[ORION_REDACTED_CREDENTIAL]';
const IDENTITIES=new Set(['SOUL.md','IDENTITY.md','AGENTS.md','USER.md']);
const SHARED_KEEP=new Set([
  'agent_databases','agent_provenance','audit_events','schema_meta','session_groups',
  'session_state_events','session_state_heads','session_upstream_links','session_watch_cursors',
  'skill_usage','skill_workshop_changes','state_leases','user_profiles','user_profile_identities',
  'worker_session_placements','workspace_generated_bootstrap_hashes','workspace_path_aliases','workspace_setup_state',
]);
const AGENT_DROP=new Set(['auth_profile_state','auth_profile_store','cache_entries','memory_embedding_cache']);
const SECRET_KEY=/(?:api[_-]?key|access[_-]?token|refresh[_-]?token|(?:^|[_. -])token(?:$|[_. -])|password|passphrase|private[_-]?key|^private$|hmac[_-]?key|client[_-]?secret|secretkey|secret_key|authorization|noiseKey|signedIdentityKey|signedPreKey|advSecretKey)/i;
const PATTERNS=[
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/g,
  /\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{15,})\b/g,
  /\b[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{25,110}\b/g,
];
const ASSIGNMENT=/((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret|auth[_-]?token|gateway[_-]?token|[A-Z][A-Z0-9_]*_(?:API_KEY|TOKEN|SECRET|PASSWORD))["']?\s*[:=]\s*["']?)([^\s"'<>;,}{]{8,})/gi;
const BEARER=/(\bBearer\s+)[A-Za-z0-9._~+/-]{12,}=*/gi;
const quote=s=>'"'+s.replaceAll('"','""')+'"';
const hash=b=>createHash('sha256').update(b).digest('hex');
const fail=code=>{throw Object.assign(new Error(code),{code});};
const json=(value)=>JSON.stringify(value,(_,v)=>typeof v==='bigint'?{$integer:String(v)}:
  v instanceof Uint8Array?{$bytes:Buffer.from(v).toString('base64')}:v);
const sorted=value=>Array.isArray(value)?value.map(sorted):value && typeof value==='object'?
  Object.fromEntries(Object.keys(value).sort().map(k=>[k,sorted(value[k])])):value;
const canonical=value=>JSON.stringify(sorted(value));

function tables(db) {
  const kinds=new Map(db.prepare('PRAGMA table_list').all().filter(t=>t.schema==='main').map(t=>[t.name,t]));
  return db.prepare("SELECT name,sql FROM sqlite_schema WHERE type='table' ORDER BY name").all()
    .filter(t=>!t.name.startsWith('sqlite_') && kinds.get(t.name)?.type!=='shadow')
    .map(t=>({...t,...kinds.get(t.name),columns:db.prepare('PRAGMA table_xinfo('+quote(t.name)+')').all()}));
}
function rows(db,table) {
  const columns=table.columns.filter(c=>c.hidden===0).map(c=>c.name);
  const keys=table.wr ? table.columns.filter(c=>c.pk).sort((a,b)=>a.pk-b.pk).map(c=>c.name):['rowid'];
  const select=(table.wr?'':'rowid AS "__orion_rowid__", ')+columns.map(quote).join(',');
  const query=db.prepare('SELECT '+select+' FROM '+quote(table.name)+' ORDER BY '+keys.map(quote).join(','));
  query.setReadBigInts(true);
  return query.all();
}
function logicalEvent(row) {
  const compressed=row.event_zstd==null?null:zstdDecompressSync(row.event_zstd,{maxOutputLength:64*1024*1024}).toString('utf8');
  const text=row.event_json ?? compressed;
  if(typeof text!=='string') fail('TRANSCRIPT_PAYLOAD_MISSING');
  const event=JSON.parse(text);
  if(row.event_json!=null&&compressed!=null&&canonical(event)!==canonical(JSON.parse(compressed)))
    fail('TRANSCRIPT_REPRESENTATIONS_DISAGREE');
  return event;
}
function fingerprintRows(entries,table,key) {
  const h=key?createHmac('sha256',key):createHash('sha256');
  const records=entries.map(row=>{
    const {__orion_rowid__,...data}=row;
    const identity=table.type==='virtual'?{__orion_rowid__,...data}:data;
    if(table.name==='transcript_events') {
      const {event_json,event_zstd,event_utf8_bytes,...rest}=identity;
      return json({...rest,event:sorted(logicalEvent(row))});
    }
    return json(identity);
  });
  // Logical keys and event sequence values are included in each record.
  // Physical rowids in ordinary tables may change during VACUUM.
  for(const record of records.sort())h.update(record+'\n');
  return h.digest('hex');
}
function fingerprint(db,table,key) {
  return fingerprintRows(rows(db,table),table,key);
}
function checkedFile(root,name) {
  const full=path.resolve(root,name);
  if(!full.startsWith(root+path.sep) || fs.lstatSync(full).isSymbolicLink() ||
     !fs.statSync(full).isFile() || fs.realpathSync(full)!==full) fail('SOURCE_PATH_INVALID');
  return full;
}

export async function prepare(restore=RESTORE,parent='/root') {
  const started=Date.now();
  const bounded=()=>{if(Date.now()-started>15*60*1000)fail('PREPARATION_TIME_LIMIT');};
  const report=JSON.parse(fs.readFileSync(path.join(restore,'restore-report.json'),'utf8'));
  const inventory=JSON.parse(fs.readFileSync(path.join(restore,'inventory-v1.json'),'utf8'));
  const archiveRows=fs.readFileSync(path.join(restore,'restored-files.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  const archiveHashes=new Map(archiveRows.map(row=>[row.path,row.sha256]));
  if(report.result!=='RESTORE_PASS'||inventory.result!=='INVENTORY_PASS'||
     report.archive_sha256!==ARCHIVE_HASH||inventory.archive_sha256!==ARCHIVE_HASH)fail('BASELINE_MISMATCH');
  const restored=fs.realpathSync(path.join(restore,'restored'));
  const main=report.databases.find(d=>d.path.endsWith('/agents/main/agent/openclaw-agent.sqlite'));
  if(!main)fail('MAIN_DATABASE_MISSING');
  const stateRoot=path.dirname(path.dirname(path.dirname(path.dirname(checkedFile(restored,main.path)))));
  const requested=[
    ['main','agents/main/agent/openclaw-agent.sqlite',25],
    ['openclaw','agents/openclaw/agent/openclaw-agent.sqlite',25],
    ['shared','state/openclaw.sqlite',20],
  ];
  const output=fs.mkdtempSync(path.join(parent,'orion-export-review-'));
  fs.chmodSync(output,0o700);
  const payload=path.join(output,'candidate');
  fs.mkdirSync(payload,{mode:0o700});
  const key=randomBytes(32);
  fs.writeFileSync(path.join(output,'private-fingerprint.key'),key,{mode:0o600,flag:'wx'});
  const secretValues=new Set();
  const secretBytes=[];
  function remember(value) {
    if(typeof value==='string' && value.length>=12 && value!==MARKER) secretValues.add(value);
    if(value instanceof Uint8Array) {
      if(value.byteLength>=12)secretBytes.push(Buffer.from(value));
      secretValues.add(Buffer.from(value).toString('base64'));
      secretValues.add(Buffer.from(value).toString('hex'));
    }
  }
  function harvest(value,keyName='') {
    if(value==null)return;
    if(SECRET_KEY.test(keyName)&&value.type==='Buffer'&&Array.isArray(value.data))remember(Buffer.from(value.data));
    if(typeof value==='string') {
      if(SECRET_KEY.test(keyName))remember(value);
      for(const regex of PATTERNS)for(const m of value.matchAll(regex))remember(m[0]);
      for(const m of value.matchAll(ASSIGNMENT))remember(m[2]);
      for(const m of value.matchAll(BEARER))remember(m[0].slice(m[1].length));
      if(/^\s*[{[]/.test(value)) {try{harvest(JSON.parse(value));}catch{}}
    } else if(value instanceof Uint8Array) {
      if(SECRET_KEY.test(keyName))remember(value);
    } else if(typeof value==='object')for(const [k,v]of Object.entries(value))harvest(v,k);
  }
  const sources=[],ledger=[],originals=[];
  let current={stage:'source opening'};
  try {
    for(const [role,relative,version]of requested) {
      const file=checkedFile(stateRoot,relative);
      const archivedPath=path.relative(restored,file);
      if(hash(fs.readFileSync(file))!==inventory.database_file_sha256[archivedPath])fail('SOURCE_DATABASE_CHANGED');
      let walHash;
      if(fs.existsSync(file+'-wal')) {
        walHash=hash(fs.readFileSync(file+'-wal'));
        if(walHash!==archiveHashes.get(archivedPath+'-wal'))fail('SOURCE_WAL_CHANGED');
      } else if(archiveHashes.has(archivedPath+'-wal'))fail('SOURCE_WAL_MISSING');
      const db=new DatabaseSync(file,{readOnly:true});
      sources.push({role,relative,file,db,version,walHash,before:hash(fs.readFileSync(file))});
      if(db.prepare('PRAGMA user_version').get().user_version!==version)fail('SOURCE_SCHEMA_MISMATCH');
      for(const table of tables(db)) {
        bounded();current={stage:'credential inventory',role,table:table.name};
        for(const row of rows(db,table)) {
          for(const [column,value]of Object.entries(row))harvest(value,column);
          for(const label of ['field','key','state_key','entry_key']) {
            if(typeof row[label]==='string'&&SECRET_KEY.test(row[label])) {
              for(const column of ['value','value_json'])if(row[column]!=null)harvest(row[column],row[label]);
            }
          }
          if(table.name==='transcript_events')harvest(logicalEvent(row));
        }
      }
    }
    // Harvest credential/config JSON only in the disposable recovered tree.
    const skip=new Set(['node_modules','.git','extensions','plugins','tmp','cache']);
    const markdown=[];
    function walk(dir) {
      for(const e of fs.readdirSync(dir,{withFileTypes:true})) {
        bounded();
        const full=path.join(dir,e.name);
        if(e.isDirectory()&&!skip.has(e.name))walk(full);
        else if(e.isFile()&&e.name.endsWith('.json')&&fs.statSync(full).size<=16*1024*1024) {
          try{harvest(JSON.parse(fs.readFileSync(full,'utf8')));}catch{}
        }
      }
    }
    walk(stateRoot);
    for(const entry of archiveRows) {
      const full=path.resolve(restored,entry.path);
      const relative=path.relative(stateRoot,full);
      if(relative.startsWith('..')||!relative.startsWith('workspace/')||!relative.endsWith('.md'))continue;
      if(relative.split(path.sep).some(p=>skip.has(p)||p==='skills'))continue;
      const file=checkedFile(stateRoot,relative),bytes=fs.readFileSync(file);
      if(hash(bytes)!==entry.sha256)fail('WORKSPACE_BASELINE_CHANGED');
      harvest(bytes.toString('utf8'));
      markdown.push({relative,bytes});
    }
    if([...IDENTITIES].some(n=>!markdown.some(f=>f.relative==='workspace/'+n)))fail('REQUIRED_IDENTITY_MISSING');
    const secrets=[...secretValues].filter(s=>s.length>=12).sort((a,b)=>b.length-a.length);
    function redactText(text) {
      let out=text;
      for(const secret of secrets)out=out.split(secret).join(MARKER);
      for(const regex of PATTERNS)out=out.replace(regex,MARKER);
      out=out.replace(ASSIGNMENT,(_,prefix)=>prefix+MARKER).replace(BEARER,(_,prefix)=>prefix+MARKER);
      return out;
    }
    function redactObject(value,keyName='') {
      if(value!==null&&typeof value==='object'&&SECRET_KEY.test(keyName))return MARKER;
      if(typeof value==='string') {
        if(SECRET_KEY.test(keyName)&&value.length>0&&value!==MARKER)return MARKER;
        return redactText(value);
      }
      if(Array.isArray(value))return value.map(v=>redactObject(v));
      if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,redactObject(v,k)]));
      return value;
    }
    function sanitizeText(value,column) {
      let out=redactText(value);
      if(/^\s*[{[]/.test(out)) {
        try {
          const parsed=JSON.parse(out),clean=redactObject(parsed);
          if(canonical(parsed)!==canonical(clean))out=JSON.stringify(clean);
        } catch {}
      } else if(SECRET_KEY.test(column)&&out.length>0&&out!==MARKER)out=MARKER;
      return out;
    }
    function transform(row,table,role) {
      const changes={};
      if(table.name==='transcript_events') {
        const event=logicalEvent(row);
        const text=JSON.stringify(event);
        const cleaned=sanitizeText(text,'event_json');
        if(canonical(event)!==canonical(JSON.parse(cleaned))) {
          if(row.event_json!=null)changes.event_json=cleaned;
          if(row.event_zstd!=null)changes.event_zstd=zstdCompressSync(Buffer.from(cleaned));
          changes.event_utf8_bytes=BigInt(Buffer.byteLength(cleaned));
        }
      }
      for(const column of table.columns.filter(c=>c.hidden===0)) {
        const name=column.name,value=row[name];
        if(table.name==='transcript_events'&&['event_json','event_zstd','event_utf8_bytes'].includes(name))continue;
        if(typeof value==='string') {
          const cleaned=sanitizeText(value,name);
          if(cleaned!==value)changes[name]=cleaned;
        } else if(value instanceof Uint8Array) {
          const allowed=(table.name==='memory_index_chunks'&&name==='embedding')||
            (table.name==='user_profiles'&&name==='avatar');
          if(!allowed)fail('UNREVIEWED_RETAINED_BLOB');
          if(secretBytes.some(secret=>Buffer.from(value).includes(secret)))fail('SECRET_IN_RETAINED_BLOB');
          for(const secret of secrets)if(Buffer.from(value).includes(Buffer.from(secret)))fail('SECRET_IN_RETAINED_BLOB');
        }
      }
      if(role==='shared'&&table.name==='agent_databases') {
        if(!['main','openclaw'].includes(row.agent_id))fail('UNREVIEWED_AGENT_REGISTRATION');
        const target='/home/replay/.openclaw/agents/'+row.agent_id+'/agent/openclaw-agent.sqlite';
        if(row.path!==target)changes.path=target;
      }
      return changes;
    }
    const files=[],baselines=[];
    for(const source of sources) {
      const {role,relative,db}=source;
      current={stage:'candidate rebuild',role};
      const intermediate=path.join(output,role+'-working.sqlite');
      await backup(db,intermediate);
      const copy=new DatabaseSync(intermediate);
      const expected=new Map();
      let rebuilt=false;
      try {
        copy.exec('PRAGMA foreign_keys=OFF; BEGIN IMMEDIATE');
        for(const table of tables(db)) {
          bounded();current={stage:'table sanitization',role,table:table.name};
          const sourceRows=rows(db,table);
          originals.push({database:relative,table:table.name,rows:sourceRows.length,fingerprint_hmac:fingerprint(db,table,key)});
          const keep=role==='shared'?SHARED_KEEP.has(table.name):!AGENT_DROP.has(table.name);
          if(!keep) {
            if(sourceRows.length)copy.exec('DELETE FROM '+quote(table.name));
            ledger.push({database:relative,table:table.name,action:'excluded-data',rows:sourceRows.length});
            continue;
          }
          const transformed=sourceRows.map(row=>({...row,...transform(row,table,role)}));
          expected.set(table.name,fingerprintRows(transformed,table));
          let modifiedRows=0,modifiedCells=0;
          for(const row of sourceRows) {
            const changes=transform(row,table,role),names=Object.keys(changes);
            if(!names.length)continue;
            const keys=table.wr?table.columns.filter(c=>c.pk).sort((a,b)=>a.pk-b.pk).map(c=>c.name):['rowid'];
            const condition=keys.map(k=>quote(k)+' IS ?').join(' AND ');
            const values=keys.map(k=>k==='rowid'?row.__orion_rowid__:row[k]);
            const update=copy.prepare('UPDATE '+quote(table.name)+' SET '+names.map(n=>quote(n)+'=?').join(',')+' WHERE '+condition);
            update.run(...names.map(n=>changes[n]),...values);
            modifiedRows++;modifiedCells+=names.length;
          }
          const afterRows=rows(copy,table);
          if(afterRows.length!==sourceRows.length)fail('RETAINED_ROW_COUNT_CHANGED');
          ledger.push({database:relative,table:table.name,action:'retained',rows:sourceRows.length,modifiedRows,modifiedCells});
        }
        copy.exec('COMMIT');
        for(const table of tables(copy).filter(t=>t.type==='virtual')) {
          if(!/\bUSING\s+fts5\b/i.test(table.sql))fail('UNREVIEWED_VIRTUAL_TABLE');
          copy.prepare('INSERT INTO '+quote(table.name)+'('+quote(table.name)+") VALUES('rebuild')").run();
          copy.prepare('INSERT INTO '+quote(table.name)+'('+quote(table.name)+") VALUES('optimize')").run();
        }
        if(copy.prepare('PRAGMA foreign_key_check').all().length)fail('CANDIDATE_FOREIGN_KEY_FAILURE');
        const dest=path.join(payload,relative);
        fs.mkdirSync(path.dirname(dest),{recursive:true,mode:0o700});
        copy.prepare('VACUUM INTO ?').run(dest);
        fs.chmodSync(dest,0o600);
        const verified=new DatabaseSync(dest,{readOnly:true});
        try {
          if(verified.prepare('PRAGMA integrity_check').all().some(r=>r.integrity_check!=='ok'))fail('CANDIDATE_INTEGRITY_FAILURE');
          if(verified.prepare('PRAGMA user_version').get().user_version!==source.version)fail('CANDIDATE_SCHEMA_CHANGED');
          for(const table of tables(verified)) {
            bounded();current={stage:'candidate verification',role,table:table.name};
            const keep=role==='shared'?SHARED_KEEP.has(table.name):!AGENT_DROP.has(table.name);
            const found=rows(verified,table);
            if(!keep&&found.length)fail('EXCLUDED_ROWS_REMAIN');
            if(keep&&fingerprintRows(found,table)!==expected.get(table.name))fail('RETAINED_CONTENT_MISMATCH');
            if(keep)for(const row of found)if(Object.keys(transform(row,table,role)).length)fail('REDACTION_NOT_STABLE');
            baselines.push({database:relative,table:table.name,rows:found.length,fingerprint_sha256:fingerprint(verified,table)});
          }
        } finally {verified.close();}
        // Rebuilding removes free pages. Check recognizable credential bytes again.
        const bytes=fs.readFileSync(dest);
        for(const secret of secrets) {
          if(bytes.includes(Buffer.from(secret))||bytes.includes(Buffer.from(secret,'utf16le')))fail('SECRET_BYTES_REMAIN');
        }
        if(secretBytes.some(secret=>bytes.includes(secret)))fail('SECRET_BYTES_REMAIN');
        files.push({path:relative,bytes:bytes.length,sha256:hash(bytes)});
        rebuilt=true;
      } finally {copy.close();if(rebuilt)fs.unlinkSync(intermediate);}
    }
    for(const item of markdown) {
      current={stage:'workspace sanitization',file:item.relative};
      const original=new TextDecoder('utf-8',{fatal:true}).decode(item.bytes),clean=sanitizeText(original,'markdown');
      if(IDENTITIES.has(path.basename(item.relative))&&clean!==original)fail('IDENTITY_REDACTION_REQUIRES_REVIEW');
      const dest=path.join(payload,item.relative);
      fs.mkdirSync(path.dirname(dest),{recursive:true,mode:0o700});
      fs.writeFileSync(dest,clean,{mode:0o600,flag:'wx'});
      files.push({path:item.relative,bytes:Buffer.byteLength(clean),sha256:hash(Buffer.from(clean))});
      ledger.push({file:item.relative,action:'retained',changed:clean!==original});
    }
    for(const source of sources) {
      if(hash(fs.readFileSync(source.file))!==source.before)fail('SOURCE_DATABASE_CHANGED');
      if(source.walHash!==undefined&&(!fs.existsSync(source.file+'-wal')||
         hash(fs.readFileSync(source.file+'-wal'))!==source.walHash))fail('SOURCE_WAL_CHANGED');
    }
    const manifest={format:'orion-reviewed-candidate-v1',archive_sha256:ARCHIVE_HASH,files,baselines,changes:ledger,
      excluded_file_classes:['credentials','config','plugins','caches','logs','quarantine','temporary captures','generation lock companions','non-Markdown workspace assets','workspace skills'],
      no_config_included:true,target_state_root:'/home/replay/.openclaw',upload_ready:false};
    fs.writeFileSync(path.join(payload,'manifest.json'),JSON.stringify(manifest,null,2)+'\n',{mode:0o600,flag:'wx'});
    fs.writeFileSync(path.join(output,'private-original-baseline.json'),JSON.stringify(originals,null,2)+'\n',{mode:0o600,flag:'wx'});
    const review={result:'EXPORT_CANDIDATE_REVIEW_REQUIRED',directory:output,candidate:payload,files:files.length,
      retained_records:baselines.filter(t=>['conversations','transcript_events','memory_index_chunks'].includes(t.table)),
      excluded_nonempty_tables:ledger.filter(r=>r.action==='excluded-data'&&r.rows),
      changed_tables:ledger.filter(r=>r.modifiedRows),identity_files:files.filter(f=>IDENTITIES.has(path.basename(f.path))),
      secret_detection:'Known credential values, credential fields and recognizable patterns checked; user review remains required.',
      upload_ready:false};
    fs.writeFileSync(path.join(output,'export-review.json'),JSON.stringify(review,null,2)+'\n',{mode:0o600,flag:'wx'});
    return review;
  } catch(error) {
    fs.writeFileSync(path.join(output,'private-preparation-error.txt'),String(error.stack||error),{mode:0o600});
    return {result:'STOP',directory:output,...current,error_code:error.code||'CANDIDATE_PREPARATION_ERROR',upload_ready:false};
  } finally {for(const source of sources)source.db.close();}
}

if(process.argv[1]&&fs.realpathSync(process.argv[1])===fs.realpathSync(new URL(import.meta.url))) {
  process.umask(0o077);
  try {
    const result=await prepare();
    console.log(JSON.stringify(result,null,2));
    if(result.result==='STOP')process.exitCode=1;
  } catch(error) {
    console.log(JSON.stringify({result:'STOP',error_code:error.code||'CANDIDATE_PREFLIGHT_FAILED',upload_ready:false}));
    process.exitCode=1;
  }
}
