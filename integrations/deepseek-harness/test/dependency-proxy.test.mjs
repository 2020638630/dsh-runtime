import assert from 'node:assert/strict'
import http from 'node:http'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'

test('rc.4 proxy routes Node fetch through the overridden undici and restores direct routing', async () => {
  const root = createRequire(import.meta.url)
  const subprocess = createRequire(root.resolve('@deepseek-ai/dsh-subprocess/package.json'))
  const proxyPath = subprocess.resolve('@deepseek-ai/dsh-http-proxy')
  const proxyRequire = createRequire(proxyPath)
  assert.equal(proxyRequire('undici/package.json').version, '8.12.2')
  const { getGlobalDispatcher } = proxyRequire('undici')
  const { installProxyFromEnvironment, proxyRouteFor } = await import(pathToFileURL(proxyPath).href)
  const seen = []
  const server = http.createServer((request, response) => {
    seen.push(request.url)
    response.end('proxy-ok')
  })
  const directSeen = []
  const directServer = http.createServer((request, response) => {
    directSeen.push(request.url)
    response.end('direct-ok')
  })
  const outerSeen = []
  const outerServer = http.createServer((request, response) => {
    outerSeen.push(request.url)
    response.end('outer-ok')
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  await new Promise((resolve) => directServer.listen(0, '127.0.0.1', resolve))
  await new Promise((resolve) => outerServer.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const values = { http_proxy: `http://127.0.0.1:${address.port}` }
  const outerValues = { http_proxy: `http://127.0.0.1:${outerServer.address().port}` }
  const reports = []
  let dispose
  let disposeOuter
  const originalDispatcher = getGlobalDispatcher()
  try {
    disposeOuter = await installProxyFromEnvironment({ get: (name) => outerValues[name] ? { value: outerValues[name] } : undefined }, (message) => reports.push(message))
    const outerDispatcher = getGlobalDispatcher()
    const outerRoute = proxyRouteFor(new URL('http://example.invalid/path'))
    dispose = await installProxyFromEnvironment({ get: (name) => values[name] ? { value: values[name] } : undefined }, (message) => reports.push(message))
    assert.deepEqual(reports, [])
    assert.equal(proxyRouteFor(new URL('http://example.invalid/path')).proxied, true)
    assert.equal(proxyRouteFor(new URL('http://127.0.0.1/')).proxied, false)
    const response = await fetch('http://example.invalid/path', { signal: AbortSignal.timeout(5000) })
    assert.equal(await response.text(), 'proxy-ok')
    assert.deepEqual(seen, ['http://example.invalid/path'])
    const directResponse = await fetch(`http://127.0.0.1:${directServer.address().port}/local`, { signal: AbortSignal.timeout(5000) })
    assert.equal(await directResponse.text(), 'direct-ok')
    assert.deepEqual(directSeen, ['/local'])
    assert.deepEqual(seen, ['http://example.invalid/path'])
    await dispose()
    dispose = undefined
    assert.equal(getGlobalDispatcher(), outerDispatcher)
    assert.deepEqual(proxyRouteFor(new URL('http://example.invalid/path')), outerRoute)
    const restoredResponse = await fetch('http://example.invalid/restored', { signal: AbortSignal.timeout(5000) })
    assert.equal(await restoredResponse.text(), 'outer-ok')
    assert.deepEqual(outerSeen, ['http://example.invalid/restored'])
  } finally {
    if (dispose) await dispose()
    if (disposeOuter) await disposeOuter()
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
    await new Promise((resolve, reject) => directServer.close((error) => error ? reject(error) : resolve()))
    await new Promise((resolve, reject) => outerServer.close((error) => error ? reject(error) : resolve()))
  }
  assert.equal(getGlobalDispatcher(), originalDispatcher)
  assert.equal(proxyRouteFor(new URL('http://example.invalid/path')).proxied, false)
})
