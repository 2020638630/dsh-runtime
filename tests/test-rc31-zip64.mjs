import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, mkdir, writeFile, readdir } from 'node:fs/promises';
import { resolve, join, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

const [mode, hostArg, outArg] = process.argv.slice(2);
const host = resolve(hostArg || '');
const out = resolve(outArg || '');
const fixture = resolve('tests/fixtures/rc31-zip64');
const dirs = (await readdir(join(host, 'node_modules/.pnpm'))).filter(x => x.startsWith('@deepseek-ai+dsh-office-to-'));
assert.equal(dirs.length, 1);
const providerPackage = join(host, 'node_modules/.pnpm', dirs[0], 'node_modules/@deepseek-ai/dsh-office-to-pdf/package.json');
const req = createRequire(providerPackage);
const kitPackage = req.resolve('@deepseek-ai/libreoffice-kit/package.json');
const kitReq = createRequire(kitPackage);
const fflatePackage = kitReq.resolve('fflate/package.json');
const fflateInfo = JSON.parse(await readFile(fflatePackage));
const fflatePath = resolve(dirname(fflatePackage), fflateInfo.exports['.'].node.import.default);
const kitVersion = JSON.parse(await readFile(kitPackage)).version;
const fflateVersion = JSON.parse(await readFile(fflatePackage)).version;
const meta = { node: process.execPath, nodeVersion: process.version, host, providerPackage, kitPackage, kitVersion, worker: join(dirname(kitPackage), 'lib/worker.js'), fflatePath, fflatePackage, fflateVersion };
assert.equal(kitVersion, '0.1.5'); assert.equal(fflateVersion, '0.8.3');
if (mode === 'child') {
  const scenario = process.argv[5];
  if (scenario === 'fflate') {
    const { unzipSync } = await import(pathToFileURL(fflatePath).href);
    try { unzipSync(await readFile(join(fixture, 'missing-extra.docx'))); throw new Error('unzipSync unexpectedly succeeded'); }
    catch (e) { assert.equal(e.code, 13); assert.equal(e.message, 'invalid zip data'); console.log(JSON.stringify({scenario, outcome:'expected-error', code:e.code, message:e.message})); }
  } else {
    const { createConverter } = await import(pathToFileURL(kitReq.resolve('@deepseek-ai/libreoffice-kit')).href);
    const converter = await createConverter({ timeoutMs: 30000 });
    try {
      const inputPath = join(fixture, scenario === 'control' ? 'control.docx' : 'missing-extra.docx');
      const outputPath = join(out, `${scenario}.pdf`);
      try {
        const result = await converter.convert({inputPath, outputPath});
        assert.equal(scenario, 'control', 'malformed input unexpectedly succeeded');
        const pdf = await readFile(outputPath); assert.equal(pdf.subarray(0,5).toString(), '%PDF-'); assert.ok(pdf.length > 100);
        console.log(JSON.stringify({scenario, outcome:'rendered', pdfBytes:pdf.length, result}));
      } catch(e) {
        if (scenario === 'control') throw e;
        console.log(JSON.stringify({scenario, outcome:'rejected', name:e.name, code:e.code, message:e.message, cause:e.cause?.message}));
        assert.equal(e.code,'invalid-document');
        assert.equal(e.message, 'Input is not a supported, bounded OOXML archive.');
      }
    } finally { await converter.dispose(); }
  }
} else {
  assert.equal(mode, 'run'); assert.ok(hostArg && outArg, 'host and new evidence directory are required');
  await mkdir(out);
  console.log(JSON.stringify({meta})); await writeFile(join(out,'identity.json'),JSON.stringify(meta,null,2));
  for (const scenario of ['control','consumer','fflate']) {
    const child=spawn(process.execPath,[resolve('tests/test-rc31-zip64.mjs'),'child',host,out,scenario],{stdio:['ignore','pipe','pipe']});
    let stdout='',stderr='',timedOut=false; child.stdout.on('data',d=>stdout+=d); child.stderr.on('data',d=>stderr+=d);
    const exit=await new Promise((res,rej)=>{
      let timer, deadline, killer, settled=false, closed, killComplete=false;
      const finish=(error, result)=>{
        if (settled) return;
        settled=true;
        clearTimeout(timer); clearTimeout(deadline);
        if (killer) { killer.kill(); killer.unref(); }
        if (error) { child.stdout.destroy(); child.stderr.destroy(); child.unref(); rej(error); }
        else res(result);
      };
      child.once('error',e=>finish(e));
      child.once('close',(code,signal)=>{
        closed={code,signal};
        if (!timedOut || killComplete) finish(null,closed);
      });
      timer=setTimeout(()=>{
        timedOut=true;
        deadline=setTimeout(()=>finish(new Error(`${scenario}: process did not close after termination`)),10000);
        if (process.platform === 'win32') {
          killer=spawn('taskkill.exe',['/pid',String(child.pid),'/t','/f'],{stdio:'ignore'});
          killer.once('error',e=>finish(new Error(`${scenario}: taskkill failed: ${e.message}`)));
          killer.once('close',code=>{
            if (code !== 0) finish(new Error(`${scenario}: taskkill failed with exit code ${code}`));
            else { killComplete=true; if (closed) finish(null,closed); }
          });
        } else if (!child.kill('SIGKILL')) finish(new Error(`${scenario}: failed to terminate child`));
        else { killComplete=true; if (closed) finish(null,closed); }
      },60000);
    });
    const record={scenario,...exit,timedOut,stdout,stderr}; console.log(JSON.stringify(record)); await writeFile(join(out,`${scenario}.json`),JSON.stringify(record,null,2));
    assert.equal(timedOut,false,`${scenario} timed out`); assert.equal(exit.signal,null); assert.equal(exit.code,0,`${scenario} failed`);
  }
}
