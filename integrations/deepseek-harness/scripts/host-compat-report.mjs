/** Read-only inventory for triaging an official Host update. No compatibility verdict. */
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync, realpathSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const hash = bytes => createHash('sha256').update(bytes).digest('hex')
const readJson = path => JSON.parse(readFileSync(path, 'utf8'))
const SOURCE_EXTENSIONS = /\.(?:ts|tsx|mts|cts|js|jsx|mjs|cjs)$/u

function artifactFiles(root) {
  const files = []
  function walk(path) {
    for (const entry of readdirSync(path, { withFileTypes: true })) {
      const child = join(path, entry.name)
      if (entry.isDirectory() && !['node_modules', '.git', '.pnpm'].includes(entry.name)) walk(child)
      else if (entry.isFile() && child !== join(root, 'package.json')) files.push(child)
      else if (entry.isSymbolicLink()) throw new Error(`unresolved package symlink: ${child}`)
    }
  }
  // Include bin, exports, assets and configuration, not just lib/dist. This is
  // a conservative installed-package digest; docs-only changes may raise the gate.
  walk(root)
  return files.sort((a, b) => relative(root, a).localeCompare(relative(root, b), 'en'))
}

function packageRecord(root) {
  const packagePath = join(root, 'package.json')
  const metadata = readJson(packagePath)
  const files = artifactFiles(root)
  const content = createHash('sha256')
  for (const path of files) {
    content.update(relative(root, path).replaceAll('\\', '/'))
    content.update('\0')
    content.update(hash(readFileSync(path)))
    content.update('\0')
  }
  return {
    name: metadata.name, version: metadata.version,
    package_sha256: hash(readFileSync(packagePath)),
    artifacts_sha256: content.digest('hex'), artifact_files: files.length,
  }
}

function importedPackages(pluginRoot) {
  const found = new Set(['@deepseek-ai/dsh'])
  const src = join(pluginRoot, 'src')
  const add = specifier => {
    const match = /^(@deepseek-ai\/[^/]+)(?:\/|$)/u.exec(specifier)
    if (match) found.add(match[1])
  }
  function walk(path) {
    for (const entry of readdirSync(path, { withFileTypes: true })) {
      const child = join(path, entry.name)
      if (entry.isDirectory()) walk(child)
      else if (entry.isFile() && SOURCE_EXTENSIONS.test(entry.name)) {
        const source = readFileSync(child, 'utf8')
        const parsed = ts.createSourceFile(child, source, ts.ScriptTarget.Latest, true)
        const visit = node => {
          if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteralLike(node.moduleSpecifier)) {
            add(node.moduleSpecifier.text)
          } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)
            && node.moduleReference.expression && ts.isStringLiteralLike(node.moduleReference.expression)) {
            add(node.moduleReference.expression.text)
          } else if (ts.isCallExpression(node) && node.arguments.length === 1 && ts.isStringLiteralLike(node.arguments[0])
            && (node.expression.kind === ts.SyntaxKind.ImportKeyword
              || (ts.isIdentifier(node.expression) && node.expression.text === 'require'))) {
            add(node.arguments[0].text)
          }
          ts.forEachChild(node, visit)
        }
        visit(parsed)
      }
    }
  }
  if (existsSync(src)) walk(src)
  const scripts = join(pluginRoot, 'scripts')
  if (existsSync(scripts)) walk(scripts)
  return [...found].sort()
}

function directPackageRoot(root, name) {
  const suffix = name.slice('@deepseek-ai/'.length)
  const direct = join(root, 'node_modules', '@deepseek-ai', suffix)
  return existsSync(join(direct, 'package.json')) ? direct : null
}

function reachableHostRoots(hostRoot) {
  const found = new Map()
  const visited = new Set()
  const pending = [directPackageRoot(hostRoot, '@deepseek-ai/dsh')].filter(Boolean)
  while (pending.length) {
    const root = realpathSync(pending.pop())
    if (visited.has(root)) continue
    visited.add(root)
    const metadata = readJson(join(root, 'package.json'))
    if (metadata.name?.startsWith('@deepseek-ai/')) {
      const roots = found.get(metadata.name) ?? []
      roots.push(root)
      found.set(metadata.name, roots)
    }
    const nodeModules = metadata.name?.startsWith('@') ? dirname(dirname(root)) : dirname(root)
    for (const name of Object.keys({ ...metadata.dependencies, ...metadata.optionalDependencies, ...metadata.peerDependencies })) {
      const local = join(nodeModules, name)
      const linked = existsSync(join(local, 'package.json')) ? local : join(hostRoot, 'node_modules', name)
      if (existsSync(join(linked, 'package.json'))) pending.push(linked)
    }
  }
  return found
}

function candidateRoots(pluginRoot, name) {
  const suffix = name.slice('@deepseek-ai/'.length)
  const nodeModules = join(pluginRoot, 'node_modules')
  const direct = directPackageRoot(pluginRoot, name)
  // pnpm keeps old store entries after an upgrade. A direct link is the
  // package this root resolves; stale store entries are not installed variants.
  if (direct) return [direct]
  const roots = []
  const store = join(nodeModules, '.pnpm')
  if (existsSync(store)) {
    for (const entry of readdirSync(store)) {
      // pnpm shortens long peer-qualified directory names on Windows, so the
      // folder name alone cannot identify a package. Check its package path.
      const candidate = join(store, entry, 'node_modules', '@deepseek-ai', suffix)
      if (existsSync(join(candidate, 'package.json'))) roots.push(candidate)
    }
  }
  return roots.filter(root => existsSync(join(root, 'package.json')))
}

export function collectHostSnapshot(hostRoot, pluginRoot, importsRoot = pluginRoot) {
  const requested = importedPackages(importsRoot)
  const packages = {}
  const issues = []
  const hostReachable = reachableHostRoots(hostRoot)
  for (const name of requested) {
    // Only count Host packages reachable from the installed Host dependency
    // graph or directly linked at the runner root. Old pnpm store entries alone
    // are not active installations. The external Profile can add more variants.
    const directHost = directPackageRoot(hostRoot, name)
    const roots = [...(hostReachable.get(name) ?? []), ...(directHost ? [directHost] : []), ...candidateRoots(pluginRoot, name)]
    const records = roots.map(packageRecord)
      .filter(record => record.name === name)
    const unique = [...new Map(records.map(record => [JSON.stringify(record), record])).values()]
    if (unique.length !== 1) {
      issues.push({ package: name, reason: unique.length === 0 ? 'missing' : 'ambiguous-installed-variants',
        versions: [...new Set(unique.map(record => record.version))].sort() })
      continue
    }
    packages[name] = unique[0]
  }
  const lockPath = join(hostRoot, 'pnpm-lock.yaml')
  const hostPackage = join(hostRoot, 'package.json')
  const runner = existsSync(hostPackage) ? readJson(hostPackage) : null
  if (!runner) issues.push({ package: 'host-runner', reason: 'missing-package-json' })
  if (!existsSync(lockPath)) issues.push({ package: 'host-runner', reason: 'missing-pnpm-lockfile' })
  if (runner?.dependencies?.['@deepseek-ai/dsh'] !== packages['@deepseek-ai/dsh']?.version) {
    issues.push({ package: 'host-runner', reason: 'declared-host-version-mismatch' })
  }
  return {
    schema_version: 2,
    host_name: packages['@deepseek-ai/dsh']?.name ?? null,
    host_version: packages['@deepseek-ai/dsh']?.version ?? null,
    host_runner_dependency: runner?.dependencies?.['@deepseek-ai/dsh'] ?? null,
    host_runner_package_sha256: runner ? hash(readFileSync(hostPackage)) : null,
    host_lock_sha256: existsSync(lockPath) ? hash(readFileSync(lockPath)) : null,
    imported_packages: requested,
    packages,
    issues,
  }
}

export function compareHostSnapshots(previous, current) {
  const result = (classification, changed_packages, artifact_changed_packages, metadata_only_packages, minimum_gate) =>
    ({ classification, changed_packages, artifact_changed_packages, metadata_only_packages, minimum_gate })
  if (previous.schema_version !== 2 || current.schema_version !== 2
    || previous.issues.length || current.issues.length) {
    return result('BLOCKED_INPUT', [], [], [], 'manual-triage')
  }
  if (JSON.stringify(previous.imported_packages) !== JSON.stringify(current.imported_packages)) {
    return result('PLUGIN_IMPORT_SET_CHANGED', [], [], [], 'focused-or-higher')
  }
  const changed = current.imported_packages.filter(name => JSON.stringify(previous.packages[name]) !== JSON.stringify(current.packages[name]))
  const artifactChanged = changed.filter(name => previous.packages[name]?.artifacts_sha256 !== current.packages[name]?.artifacts_sha256)
  const metadataOnly = changed.filter(name => !artifactChanged.includes(name))
  if (artifactChanged.some(name => name !== '@deepseek-ai/dsh')) {
    return result('IMPORTED_ARTIFACT_CHANGED', changed, artifactChanged, metadataOnly, 'focused-or-higher')
  }
  if (previous.host_lock_sha256 !== current.host_lock_sha256
    || previous.host_runner_package_sha256 !== current.host_runner_package_sha256) {
    return result('HOST_DEPENDENCY_CHANGED', changed, artifactChanged, metadataOnly, 'focused-or-higher')
  }
  if (artifactChanged.length) {
    return result('HOST_SHELL_CHANGED', changed, artifactChanged, metadataOnly, 'focused-or-higher')
  }
  if (metadataOnly.length || previous.host_runner_dependency !== current.host_runner_dependency) {
    return result('PACKAGE_METADATA_CHANGED', changed, [], metadataOnly, 'focused-or-higher')
  }
  return result('SAME_ARTIFACTS', [], [], [], 'fast-smoke')
}

function cli() {
  const args = process.argv.slice(2)
  const value = flag => {
    const index = args.indexOf(flag)
    return index < 0 ? null : args[index + 1]
  }
  const host = value('--host')
  const plugin = value('--plugin')
  const importsFrom = value('--imports-from') ?? plugin
  if (!host || !plugin) throw new Error('Usage: node host-compat-report.mjs --host HOST_RUNNER --plugin PLUGIN_ROOT [--imports-from SOURCE_ROOT] [--baseline REPORT.json]')
  const snapshot = collectHostSnapshot(host, plugin, importsFrom)
  const baseline = value('--baseline')
  const comparison = baseline ? compareHostSnapshots(readJson(baseline).snapshot, snapshot) : null
  process.stdout.write(`${JSON.stringify({ snapshot, comparison }, null, 2)}\n`)
  if (snapshot.issues.length || comparison?.classification === 'BLOCKED_INPUT') process.exitCode = 2
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  try { cli() } catch (error) { process.stderr.write(`host compatibility report failed: ${error.message}\n`); process.exitCode = 2 }
}
