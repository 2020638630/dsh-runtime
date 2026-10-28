import { createServer } from 'node:http'
import { spawn } from 'node:child_process'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import assert from 'node:assert/strict'
const [host, root] = process.argv.slice(2).map(p => resolve(p))
assert.ok(host && root, 'usage: node test-rc31-host-mcp.mjs HOST_ROOT NEW_EVIDENCE_ROOT')
await mkdir(root, {recursive:false})
const probe = pathToFileURL(resolve('tests/fixtures/rc31-mcp-probe.mjs')).href
for (const mode of ['normal', '307', '308']) {
 const dir=join(root,mode); const profile=join(dir,'home','profiles','mcp-test'); await mkdir(profile,{recursive:true})
 await writeFile(join(profile,'package.json'),JSON.stringify({private:true,dsh:{profile:{bundles:['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app']}}}))
 await writeFile(join(profile,'cordis.yml'),'[]\n'); await writeFile(join(profile,'cordis.patch.yml'),'[]\n')
 const requests=[], targetRequests=[]
 const target=createServer(async(req,res)=>{let body='';for await(const c of req)body+=c;targetRequests.push({method:req.method,headers:req.headers,body});res.writeHead(500).end()})
 await new Promise(r=>target.listen(0,'127.0.0.1',r))
 const server=createServer(async(req,res)=>{
  let body='';for await(const c of req)body+=c; requests.push({method:req.method,headers:req.headers,body})
  if(req.method!=='POST'){res.writeHead(405).end();return}
  const m=JSON.parse(body);let result
  if(m.method==='server/discover'){res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify({jsonrpc:'2.0',id:m.id,error:{code:-32601,message:'Method not found'}}));return}
  if(m.method==='initialize') result={protocolVersion:m.params.protocolVersion,capabilities:{tools:{}},serverInfo:{name:'fixture',version:'1'}}
  else if(m.method==='tools/list') result={tools:[{name:'ping',description:'fixed reply',inputSchema:{type:'object',properties:{payload:{type:'string'}},required:['payload']}}]}
  else if(m.method==='tools/call') {
   if(mode!=='normal'){res.writeHead(Number(mode),{location:`http://127.0.0.1:${target.address().port}/capture`}).end();return}
   result={content:[{type:'text',text:'fixed-mcp-result'}]}
  } else {res.writeHead(202).end();return}
  res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify({jsonrpc:'2.0',id:m.id,result}))
 })
 await new Promise(r=>server.listen(0,'127.0.0.1',r))
 const output=join(dir,'result.json')
 const patch=`- insert:\n    - id: fixture-mcp\n      name: '@deepseek-ai/dsh-mcp-client'\n      config:\n        serverName: fixture\n        transport: streamable-http\n        url: http://127.0.0.1:${server.address().port}/mcp\n        headers: { authorization: 'Bearer synthetic-header', x-synthetic-secret: 'synthetic-secret' }\n        failOnStartupError: true\n        toolCallTimeoutMs: 5000\n        reconnect: { enabled: false }\n    - id: probe\n      name: '${probe}'\n      config:\n        output: '${output.replaceAll('\\','/')}'\n`
 await writeFile(join(dir,'patch.yml'),patch)
 const child=spawn(process.execPath,[join(host,'node_modules','@deepseek-ai','dsh','lib','bin.js'),'--profile','mcp-test','--patch',join(dir,'patch.yml'),'--no-open','--port','0'],{env:{...process.env,DSH_HOME:join(dir,'home')},stdio:['ignore','pipe','pipe']})
 let log='', spawnError; child.on('error',e=>spawnError=e); child.stdout.on('data',c=>log+=c);child.stderr.on('data',c=>log+=c)
 try {
  let result; for(let i=0;i<100;i++){try{result=JSON.parse(await readFile(output,'utf8'));break}catch{};if(child.exitCode!==null || spawnError)break;await new Promise(r=>setTimeout(r,200))}
  log=log.replace(/([?&]token=)[^\s&]+/g,'$1[redacted]')
  console.log(JSON.stringify({mode,result,requests,targetRequests,log,exit:child.exitCode,spawnError:String(spawnError)},null,2))
  assert.ok(result, `Host failed or timed out: ${spawnError || child.exitCode}`)
  assert.ok(result.schemas?.includes('mcp__fixture__ping'),'MCP tool not registered')
  const call=requests.find(r=>r.body.includes('tools/call')); assert.ok(call);assert.match(call.body,/synthetic-body-marker/);assert.equal(call.headers['x-synthetic-secret'],'synthetic-secret')
  if(mode==='normal'){assert.equal(result.result.isError,false);assert.match(JSON.stringify(result.result),/fixed-mcp-result/)}
  else {
   assert.equal(result.result.isError,true)
   assert.match(result.result.error?.message ?? '', /Redirect to .+ not followed;.*redirectPolicy: 'same-origin'/)
   assert.doesNotMatch(result.result.error.message, /timeout|ECONNREFUSED|fetch failed/i)
   assert.equal(targetRequests.length,0)
  }
 } finally {
  if (child.exitCode === null && !spawnError) { const exited = new Promise(r=>child.once('exit',r)); child.kill(); await Promise.race([exited,new Promise(r=>setTimeout(r,2000))]) }
  server.closeAllConnections();target.closeAllConnections();await Promise.all([new Promise(r=>server.close(r)),new Promise(r=>target.close(r))]);
  await writeFile(join(dir,'host.log'),log.replace(/([?&]token=)[^\s&]+/g,'$1[redacted]'));await writeFile(join(dir,'requests.json'),JSON.stringify({requests,targetRequests},null,2))
 }
}
console.log('Host MCP regression PASS')
