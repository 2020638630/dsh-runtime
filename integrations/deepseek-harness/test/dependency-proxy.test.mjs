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
  const { installProxyFromEnvironment, proxyRouteFor } = await import(pathToFileURL(proxyPath).href)
  const seen = []
  const server = http.createServer((request, response) => {
    seen.push(request.url)
    response.end('proxy-ok')
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const values = { http_proxy: `http://127.0.0.1:${address.port}` }
  const reports = []
  let dispose
  try {
    dispose = await installProxyFromEnvironment({ get: (name) => values[name] ? { value: values[name] } : undefined }, (message) => reports.push(message))
    assert.deepEqual(reports, [])
    assert.equal(proxyRouteFor(new URL('http://example.invalid/path')).proxied, true)
    assert.equal(proxyRouteFor(new URL('http://127.0.0.1/')).proxied, false)
    const response = await fetch('http://example.invalid/path', { signal: AbortSignal.timeout(5000) })
    assert.equal(await response.text(), 'proxy-ok')
    assert.deepEqual(seen, ['http://example.invalid/path'])
  } finally {
    if (dispose) await dispose()
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
  }
  assert.equal(proxyRouteFor(new URL('http://example.invalid/path')).proxied, false)
})
