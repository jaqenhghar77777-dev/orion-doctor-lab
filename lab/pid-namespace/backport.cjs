'use strict';
// Transplant only the upstream reader into the already instrumented, pinned beta.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { stripTypeScriptTypes } = require('node:module');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');
const acorn = require('acorn');
const [sourcePath, dist, apiPath, rawExpectedCount] = process.argv.slice(2);
const parse = {ecmaVersion: 'latest', sourceType: 'module'};
const ts = fs.readFileSync(sourcePath);
const blob = createHash('sha1').update('blob ' + ts.length + '\0').update(ts).digest('hex');
assert.equal(blob, 'af72a74fac6f9cba849e25a9c265a7a1267f98fd');
const js = stripTypeScriptTypes(ts.toString());

function* walk(node) {
  if (!node?.type) return;
  yield node;
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) {
      for (const child of value) yield* walk(child);
    } else if (value?.type) yield* walk(value);
  }
}
function one(matches, label) {
  assert.equal(matches.length, 1, label + ' count ' + matches.length);
  return matches[0];
}
function* files(dir) {
  for (const entry of fs.readdirSync(dir, {withFileTypes:true})) {
    const f = path.join(dir, entry.name);
    if (entry.isDirectory() && entry.name !== 'node_modules') yield* files(f);
    else if (entry.isFile() && /\.(?:cjs|mjs|js)$/.test(f)) yield f;
  }
}
const upstream = [...walk(acorn.parse(js, parse))];
const helper = one(upstream.filter(n => n.type === 'FunctionDeclaration' && n.id.name === 'readLinuxPidNamespaceInode'), 'PR helper');
const sentinel = one(upstream.filter(n => n.type === 'VariableDeclarator' && n.id.name === 'LINUX_PID_NAMESPACE_UNSUPPORTED'), 'PR sentinel');
assert.equal(sentinel.init.value, 'unsupported');
const pathArg = one([...walk(helper)].filter(n => n.type === 'Literal' && n.value === '/proc/self/ns/pid'), 'PR link');
const classifiers = [];
const changed = [];
for (const file of files(dist)) {
  const input = fs.readFileSync(file, 'utf8');
  if (!input.includes('orionReplayPidPath(')) continue;
  const edits = [];
  for (const match of input.matchAll(/\bfunction\s+(readGatewayLockProcessNamespace(?:\$\d+)?)\s*\(/g)) {
    const reader = acorn.parseExpressionAt(input, match.index, parse);
    const properties = [...walk(reader)].filter(n => n.type === 'Property' && n.key.name === 'pidNsInode' &&
      input.slice(n.value.start, n.value.end).includes('orionReplayPidPath('));
    if (!properties.length) continue;
    const target = one(properties, 'beta reader in ' + file).value;
    const link = one([...walk(target)].filter(n => n.type === 'CallExpression' &&
      n.callee.property?.name === 'readlinkSync' && n.arguments[0]?.callee?.name === 'orionReplayPidPath'), 'instrumented link');
    // Keep the replay's probe redirection and upstream's real parent-directory check.
    const originalArg = input.slice(link.arguments[0].start, link.arguments[0].end);
    const fn = js.slice(helper.start, pathArg.start) + originalArg + js.slice(pathArg.end, helper.end);
    const replacement = '(() => { const fs = process.getBuiltinModule("node:fs"); const ' +
      sentinel.id.name + ' = ' + JSON.stringify(sentinel.init.value) + '; return (' + fn + ')(); })()';
    edits.push([target.start, target.end, replacement]);
    if (path.dirname(file) === dist && file.endsWith('.mjs')) {
      for (const hit of input.matchAll(/\bfunction\s+(classifyGatewayOwnerProcessNamespace(?:\$\d+)?)\s*\(/g)) {
        const classifier = acorn.parseExpressionAt(input, hit.index, parse);
        if ([...walk(classifier)].some(n => n.type === 'CallExpression' && n.callee.name === match[1])) {
          classifiers.push({file, read:match[1], classify:hit[1]});
        }
      }
    }
  }
  if (!edits.length) continue;
  let output = input;
  for (const [start,end,replacement] of edits.sort((a,b) => b[0]-a[0])) {
    output = output.slice(0,start) + replacement + output.slice(end);
  }
  fs.writeFileSync(file, output);
  changed.push(path.relative(dist,file));
}
assert.equal(changed.length, Number(rawExpectedCount), 'same set of beta PID reader bundles as fixture instrumentation');
assert.ok(classifiers.length, 'need one public adapter to the actual beta classifier for the diagnostic');
classifiers.sort((a,b) => Number(!a.file.includes('gateway-state-owner-')) - Number(!b.file.includes('gateway-state-owner-')) || a.file.localeCompare(b.file));
const api = classifiers[0];
fs.appendFileSync(api.file, '\nexport { ' + api.read + ' as orionTestRead, ' + api.classify + ' as orionTestClassify };\n');
fs.writeFileSync(apiPath, 'export { orionTestRead as read, orionTestClassify as classify } from ' + JSON.stringify(pathToFileURL(api.file).href) + ';\n');
console.log('PR_BACKPORT', JSON.stringify({upstream:'f7ae3c617269f2779767b046979b7297f56be692', blob, readers:changed, classifier:path.basename(api.file)}));
