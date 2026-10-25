/** Read-only diagnosis for one settled Runtime run after a Home copy. */
import { readFileSync, realpathSync, statSync } from 'node:fs'
import { basename, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { pathToFileURL } from 'node:url'

const RUN_ID = /^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const MAX_MANIFEST_BYTES = 1_048_576
const MAX_DIFF_BYTES = 8 * 1_048_576

function within(root, child) {
  const rel = relative(root, child)
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
}

export function checkEvidenceHome({ evidenceRoot, runId, workspaceId }) {
  if (!isAbsolute(evidenceRoot) || !RUN_ID.test(runId) || !workspaceId) {
    return { status: 'INVALID_INPUT' }
  }
  try {
    const root = realpathSync(evidenceRoot)
    const run = realpathSync(join(root, 'dsh-runtime', runId))
    if (!within(root, run) || basename(run) !== runId) return { status: 'INVALID_LOCATION' }
    const manifestPath = realpathSync(join(run, 'evidence-manifest.v1.json'))
    const diffPath = realpathSync(join(run, 'diff.patch'))
    if (!within(run, manifestPath) || !within(run, diffPath)) return { status: 'INVALID_LOCATION' }
    const manifestInfo = statSync(manifestPath)
    const diffInfo = statSync(diffPath)
    if (!manifestInfo.isFile() || !diffInfo.isFile() || manifestInfo.size > MAX_MANIFEST_BYTES
      || diffInfo.size > MAX_DIFF_BYTES) return { status: 'INVALID_FILE' }
    const manifestBytes = readFileSync(manifestPath)
    if (manifestBytes.length > MAX_MANIFEST_BYTES) return { status: 'INVALID_FILE' }
    const manifest = JSON.parse(manifestBytes.toString('utf8'))
    if (manifest?.schema_version !== '1' || manifest.run_id !== runId
      || manifest.workspace_id !== workspaceId) return { status: 'IDENTITY_MISMATCH' }
    const ref = manifest.workspace_changes?.diff_content_ref
    if (typeof ref !== 'string' || !isAbsolute(ref)) return { status: 'INVALID_REFERENCE' }
    if (resolve(ref) !== diffPath) return { status: 'RELOCATED_ABSOLUTE_REFERENCE' }
    return { status: 'READY' }
  } catch (error) {
    if (error?.code === 'ENOENT') return { status: 'MISSING_EVIDENCE' }
    return { status: 'INVALID_EVIDENCE' }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const args = process.argv.slice(2)
  const value = flag => args[args.indexOf(flag) + 1]
  const flags = ['--evidence-root', '--run-id', '--workspace-id']
  const selected = Object.fromEntries(flags.map(flag => [flag, value(flag)]))
  if (args.length !== 6 || flags.some(flag => !args.includes(flag) || !selected[flag] || selected[flag].startsWith('--'))) {
    process.stdout.write(`${JSON.stringify({ status: 'INVALID_INPUT' })}\n`)
    process.exitCode = 1
  } else {
    const result = checkEvidenceHome({ evidenceRoot: selected['--evidence-root'],
      runId: selected['--run-id'], workspaceId: selected['--workspace-id'] })
    process.stdout.write(`${JSON.stringify(result)}\n`)
    process.exitCode = result.status === 'READY' ? 0 : result.status === 'RELOCATED_ABSOLUTE_REFERENCE' ? 2 : 1
  }
}
