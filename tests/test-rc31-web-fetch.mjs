// The injected resolver makes local fixtures reachable; it does not test public DNS or internet routing.
import http from 'node:http';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';

for (const k of ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']) delete process.env[k];
const {HttpFetchProvider} = await import(pathToFileURL(process.argv[2]));
let targetCount = 0;
const listen = s => new Promise(r => s.listen(0, '127.0.0.1', () => r(s.address().port)));
const close = s => new Promise(r => s.close(r));
const target = http.createServer((req, res) => { targetCount++; res.end('target'); });
const targetPort = await listen(target);
const server = http.createServer((req, res) => {
  if (req.url === '/same') {res.writeHead(302, {location:'/normal'}); res.end();}
  else if (req.url === '/cross') {res.writeHead(302, {location:`http://other.test:${targetPort}/target`}); res.end();}
  else {res.writeHead(200, {'content-type':'text/plain'}); res.end('fixture response');}
});
const port = await listen(server);
const options = {maxResponseBytes:10000,maxBodyChars:10000,timeoutMs:5000,maxRedirects:3,userAgent:'rc31-test'};
try {
  const injected = new HttpFetchProvider(options, async () => [{address:'127.0.0.1',family:4}]);
  const base = `http://fixture.test:${port}`;
  assert.match(JSON.stringify(await injected.fetch({url:base+'/normal'})), /fixture response/);
  console.log('PASS normal response, injected resolver');
  assert.match(JSON.stringify(await injected.fetch({url:base+'/same'})), /fixture response/);
  console.log('PASS same-origin redirect, injected resolver');
  await assert.rejects(injected.fetch({url:base+'/cross'}), e => e.code === 'WEB_REDIRECT_BLOCKED');
  assert.equal(targetCount, 0);
  console.log('PASS cross-origin WEB_REDIRECT_BLOCKED, target requests=0, injected resolver');
  const normal = new HttpFetchProvider(options);
  await assert.rejects(normal.fetch({url:`http://127.0.0.1:${port}/normal`}), e => e.code === 'WEB_BLOCKED_URL');
  console.log('PASS loopback WEB_BLOCKED_URL, default resolver');
} finally { await close(server); await close(target); }
