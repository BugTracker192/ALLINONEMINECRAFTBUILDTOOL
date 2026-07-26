#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const repo = path.resolve(__dirname, '..');
let ts;
try {
  ts = require('typescript');
} catch {
  const npmRoot = cp.execFileSync('npm', ['root', '-g'], {encoding: 'utf8'}).trim();
  ts = require(path.join(npmRoot, 'typescript'));
}
const roots = ['apps/web/src', 'apps/renderer-service/src', 'packages/renderer/src', 'packages/protocol/src'];
const files = [];
for (const root of roots) {
  const walk = (dir) => {
    for (const name of fs.readdirSync(dir)) {
      const item = path.join(dir, name);
      const stat = fs.statSync(item);
      if (stat.isDirectory()) walk(item);
      else if (/\.tsx?$/.test(name)) files.push(item);
    }
  };
  walk(path.join(repo, root));
}
const failures = [];
for (const file of files.sort()) {
  const source = fs.readFileSync(file, 'utf8');
  const result = ts.transpileModule(source, {
    fileName: file,
    reportDiagnostics: true,
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
      jsx: ts.JsxEmit.ReactJSX,
      strict: true,
      isolatedModules: true,
      useDefineForClassFields: true,
    },
  });
  for (const diagnostic of result.diagnostics || []) {
    if (diagnostic.category === ts.DiagnosticCategory.Error) {
      failures.push({file: path.relative(repo, file), code: diagnostic.code, message: ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n')});
    }
  }
}
const report = {schemaVersion: 1, fileCount: files.length, failureCount: failures.length, failures};
const output = path.join(repo, 'var/reports/typescript-transpile.json');
fs.mkdirSync(path.dirname(output), {recursive: true});
fs.writeFileSync(output, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
process.exit(failures.length ? 1 : 0);
