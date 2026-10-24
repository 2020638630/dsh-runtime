import fs from 'node:fs'
import readline from 'node:readline'

const mode = process.env.DSH_CODEX_STUB_MODE ?? 'success'
if (mode === 'startup-fail') process.exit(7)

const threadId = 'stub-thread'
const turnId = 'stub-turn'
const capture = process.env.DSH_CODEX_STUB_CAPTURE
const stubStderr = process.env.DSH_CODEX_STUB_STDERR

if (stubStderr) process.stderr.write(stubStderr)

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`)
}

const input = readline.createInterface({ input: process.stdin })
input.on('line', (line) => {
  const message = JSON.parse(line)
  const method = message.method
  const id = message.id
  const params = message.params ?? {}

  if (method === 'initialize') {
    send({ jsonrpc: '2.0', id, result: {} })
  } else if (method === 'initialized') {
    return
  } else if (method === 'thread/start') {
    if (capture) fs.writeFileSync(capture, JSON.stringify(params))
    send({ jsonrpc: '2.0', id, result: { thread: { id: threadId, ephemeral: true } } })
  } else if (method === 'turn/start') {
    send({ jsonrpc: '2.0', id, result: { turn: { id: turnId } } })
    if (mode === 'eof') {
      setTimeout(() => process.exit(Number(process.env.DSH_CODEX_STUB_EXIT_CODE ?? '17')), 0)
      return
    }
    send({ jsonrpc: '2.0', method: 'turn/started', params: { threadId, turn: { id: turnId } } })
    if (mode === 'hold') return
    if (mode === 'protocol-fail') {
      send({ jsonrpc: '2.0', method: 'turn/completed', params: { threadId, turn: { id: turnId, status: 'failed' } } })
      return
    }
    if (mode === 'unsupported-model') {
      send({ jsonrpc: '2.0', method: 'turn/completed', params: {
        threadId,
        turn: { id: turnId, status: 'failed', error: { message: 'model is not supported; sensitive request detail' } },
      } })
      return
    }
    const prompt = params.input?.[0]?.text ?? ''
    const cwd = process.cwd()
    send({
      jsonrpc: '2.0',
      method: 'item/completed',
      params: {
        threadId,
        turnId,
        item: { type: 'agentMessage', phase: 'final_answer', text: `stub answer: ${prompt}; cwd=${cwd}` },
      },
    })
    send({ jsonrpc: '2.0', method: 'turn/completed', params: { threadId, turn: { id: turnId, status: 'completed' } } })
  } else if (method === 'turn/interrupt') {
    send({ jsonrpc: '2.0', id, result: {} })
  } else {
    send({ jsonrpc: '2.0', id, error: { code: -32601, message: 'unknown method' } })
  }
})
