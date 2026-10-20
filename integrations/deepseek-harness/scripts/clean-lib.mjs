import { existsSync, lstatSync, realpathSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const packageRoot = realpathSync(fileURLToPath(new URL('..', import.meta.url)))
const output = resolve(packageRoot, 'lib')
if (dirname(output) !== packageRoot) throw new Error('build output escaped package root')
if (existsSync(output)) {
  const info = lstatSync(output)
  if (!info.isDirectory() || info.isSymbolicLink()) throw new Error('build output is not a real package directory')
  rmSync(output, { recursive: true })
}
