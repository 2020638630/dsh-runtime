import { readFile, writeFile } from 'node:fs/promises'
import { realpathSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const packageRoot = realpathSync(fileURLToPath(new URL('..', import.meta.url)))
const source = join(packageRoot, 'src', 'client.js')
const target = join(packageRoot, 'lib', 'client.js')
if (dirname(target) !== join(packageRoot, 'lib')) throw new Error('client output escaped package root')
await writeFile(target, await readFile(source))
