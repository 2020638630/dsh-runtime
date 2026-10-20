import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { GovernancePinStore } from '../src/governance/pin-store.ts'

const identity = {
  policy_id: 'selection-v2',
  policy_version: '2',
  artifact_schema_version: '1',
  policy_hash: 'a'.repeat(64),
}

test('policy pin survives a new store instance and rejects a conflicting identity', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'dsh-plugin-pin-'))
  const first = new GovernancePinStore(directory)
  assert.equal(await first.read('session-test'), undefined)
  await first.pin('session-test', identity)
  const resumed = new GovernancePinStore(directory)
  assert.deepEqual(await resumed.read('session-test'), identity)
  await assert.rejects(resumed.pin('session-test', { ...identity, policy_hash: 'b'.repeat(64) }), /conflict/)
})

test('corrupt or unsafe pin file fails closed', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'dsh-plugin-pin-invalid-'))
  const pins = new GovernancePinStore(directory)
  writeFileSync(join(directory, 'session-corrupt.json'), '{')
  await assert.rejects(pins.read('session-corrupt'))
  await assert.rejects(pins.read('../escape'))
})
