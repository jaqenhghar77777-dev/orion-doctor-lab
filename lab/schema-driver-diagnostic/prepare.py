"""Instrument a build-context copy of the driver for fictional-only diagnosis."""
from pathlib import Path
import sys

context=Path(sys.argv[1])
driver=context/'schema-only.mjs'
source=driver.read_text()
header=r'''
if(process.env.ORION_FICTIONAL_DIAGNOSTIC!=='1'||fs.existsSync('/input'))throw Error('FICTIONAL_DIAGNOSTIC_SCOPE_REQUIRED');
let diagnosticOperation='input parameter validation';
function sanitizeDiagnostic(value) {
  return String(value ?? '').replace(/-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----/g,'[PRIVATE_KEY_REDACTED]')
    .replace(/synthetic-doctor-replay-token/g,'[SYNTHETIC_TOKEN_REDACTED]')
    .replace(/\b(Bearer\s+)[A-Za-z0-9._~+\/-]+/gi,'$1[REDACTED]')
    .replace(/\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})\b/g,'[TOKEN_REDACTED]')
    .replace(/((?:token|password|secret|api[_-]?key)\s*[=:]\s*)[^\s,;]+/gi,'$1[REDACTED]')
    .replace(/https?:\/\/[^\s"'<>]+/g,'[URL_REDACTED]')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g,'?').slice(0,2400);
}
function diagnosticError(error,seen=new Set(),depth=0) {
  if(depth>4||seen.has(error))return {type:'TRUNCATED'};
  seen.add(error);
  return {type:sanitizeDiagnostic(error?.name||typeof error),code:error?.code==null?null:sanitizeDiagnostic(error.code),
    message:sanitizeDiagnostic(error?.message??error),
    stack:sanitizeDiagnostic(String(error?.stack??'').split('\n').slice(0,10).join('\n')),
    ...(error?.cause?{cause:diagnosticError(error.cause,seen,depth+1)}:{}),
    ...(Array.isArray(error?.errors)?{errors:error.errors.slice(0,5).map(e=>diagnosticError(e,seen,depth+1))}:{})};
}
'''
needle='const state=\'/home/replay/.openclaw\';'
assert source.count(needle)==1
source=source.replace(needle,header+'\n'+needle)
changes=[
 ('  const params=parameters();',"  diagnosticOperation='input parameter validation';\n  const params=parameters();"),
 ("    let refused=false;","    diagnosticOperation='negative ownership probe';\n    let refused=false;"),
 ('    await withDoctorSqliteMaintenanceLock(',"    diagnosticOperation='acquire stock Doctor maintenance lock';\n    await withDoctorSqliteMaintenanceLock("),
 ('        const result=await prepareDoctorDatabaseMigrations(params);',"        diagnosticOperation='prepareDoctorDatabaseMigrations (stock backups and version migrations)';\n        const result=await prepareDoctorDatabaseMigrations(params);\n        diagnosticOperation='validate migration warnings';"),
 ('        await withAgentDatabaseMaintenanceLease(',"        diagnosticOperation='acquire stock agent maintenance lease';\n        await withAgentDatabaseMaintenanceLease("),
 ('            const db=openNodeSqliteDatabase(target.path);',"            diagnosticOperation='openNodeSqliteDatabase '+target.agentId;\n            const db=openNodeSqliteDatabase(target.path);"),
 ('            try {ensureOpenClawAgentDatabaseSchema(',"            try {diagnosticOperation='ensureOpenClawAgentDatabaseSchema '+target.agentId;ensureOpenClawAgentDatabaseSchema("),
 ('        await closeOpenClawAgentDatabasesAsync(state);',"        diagnosticOperation='closeOpenClawAgentDatabasesAsync';\n        await closeOpenClawAgentDatabasesAsync(state);"),
 ('        await closeOpenClawStateDatabaseAsync();',"        diagnosticOperation='closeOpenClawStateDatabaseAsync';\n        await closeOpenClawStateDatabaseAsync();"),
 ("  console.error(JSON.stringify({result:'STOP',code:/^[A-Z_]{3,80}$/.test(error.message)?error.message:'SCHEMA_DRIVER_FAILED',error_type:error.name}));",
  "  console.error('FICTIONAL_DIAGNOSTIC '+JSON.stringify({result:'STOP',operation:diagnosticOperation,exception:diagnosticError(error)}));")
]
for old,new in changes:
    if source.count(old)!=1:raise ValueError('Diagnostic driver anchor differs')
    source=source.replace(old,new)
driver.write_text(source)
print('FICTIONAL_DIAGNOSTIC_PREPARED build-context copy only; stock package and preservation verifier unchanged')
