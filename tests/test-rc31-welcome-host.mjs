import { spawn, spawnSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import assert from 'node:assert/strict';

const [kit, host, home, node] = process.argv.slice(2);
assert.ok(node, 'Expected kit, host, home and Node paths');
const child = spawn('pwsh', ['-NoProfile', '-File', join(kit, 'Start-QualifiedHost.ps1'), '-KitRoot', kit, '-HostRunnerRoot', host, '-HomeRoot', home, '-NodePath', node, '-Port', '0'], {stdio:['ignore','pipe','pipe'], windowsHide:true});
let output = '', launchError;
child.on('error', e => { launchError = e });
child.stdout.on('data', chunk => { output += chunk.toString() });
child.stderr.on('data', chunk => { output += chunk.toString() });
try {
  let url;
  for (let i = 0; i < 300; i++) {
    url = output.match(/http:\/\/127\.0\.0\.1:\d+\/\?token=[^\s\x1b]+/)?.[0];
    if (url || child.exitCode !== null || launchError) break;
    await new Promise(r => setTimeout(r, 200));
  }
  assert.ok(url, 'Host did not produce a local launch URL');
  const initial = await fetch(url, {redirect:'manual'});
  assert.equal(initial.status, 303);
  const cookie = initial.headers.get('set-cookie')?.split(';')[0];
  assert.ok(cookie, 'Host did not issue an authentication cookie');
  const origin = new URL(url).origin;
  async function rpc(method, args) {
    const id = crypto.randomUUID();
    const response = await fetch(`${origin}/api/${method}`, {method:'POST', headers:{'content-type':'application/json', cookie}, body:JSON.stringify({type:'client-request', rpcId:id, method, payload:{args}})});
    assert.equal(response.status, 200, `${method} HTTP failure`);
    const body = await response.json();
    assert.equal(body.rpcId, id); assert.equal(body.result?.ok, true, `${method} failed: ${body.result?.error?.code}`);
    return body.result.value;
  }
  const description = await rpc('settings/describe', {});
  const general = description.namespaces.find(row => row.ns === 'ui-settings-general');
  assert.ok(general, 'Welcome namespace missing');
  await rpc('settings/mutate', {ns:'ui-settings-general', ops:[{op:'set',path:['welcomeNoticeVersion'],value:'2026-09-28.1'}], expectedRevision:general.revision});
  const patch = await readFile(join(home, 'profiles/runtime-api-reviewer-preview/cordis.patch.yml'), 'utf8');
  assert.match(patch, /welcomeNoticeVersion:\s*2026-09-28\.1/);
  console.log('Host settings mutation wrote welcome acknowledgement');
} finally {
  if (child.pid && child.exitCode === null) spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], {stdio:'ignore', windowsHide:true});
}
