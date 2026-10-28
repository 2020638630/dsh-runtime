// Inspect the packages reached by each installed consumer, without loading them.
import { readFileSync, realpathSync, existsSync } from 'node:fs';
import { dirname, join, resolve, relative, isAbsolute } from 'node:path';
import { createHash } from 'node:crypto';

const [template, root, kind] = process.argv.slice(2);
if (!template || !root || !['host', 'profile'].includes(kind)) throw Error('usage: check-rc31-graph.mjs TEMPLATE ROOT host|profile');
const read = p => readFileSync(p);
const json = p => JSON.parse(read(p));
const sha = p => createHash('sha256').update(read(p)).digest('hex');
for (const f of ['package.json', 'pnpm-workspace.yaml', 'pnpm-lock.yaml']) {
  if (sha(join(root, f)) !== sha(join(template, f))) throw Error(`${kind}: ${f} differs from delivery policy`);
}
const physicalRoot = realpathSync(root);
function within(p) {
  const r = relative(physicalRoot, p);
  return r === '' || (!r.startsWith('..' + '/') && !r.startsWith('..' + '\\') && r !== '..' && !isAbsolute(r));
}
function locate(from, name, optional = false) {
  let dir = dirname(from);
  while (true) {
    const candidate = join(dir, 'node_modules', name, 'package.json');
    if (existsSync(candidate)) {
      const physical = realpathSync(candidate);
      if (!within(physical)) throw Error(`${kind}: ${name} resolved outside installation root: ${physical}`);
      return physical;
    }
    const parent = dirname(dir);
    if (parent === dir) {
      if (optional) return undefined;
      throw Error(`${kind}: cannot resolve ${name} from ${from}`);
    }
    dir = parent;
  }
}
const checks = {
  '@deepseek-ai/dsh-web-fetch-http>undici': '8.12.2',
  '@deepseek-ai/dsh-http-proxy>undici': '8.12.2',
  '@deepseek-ai/libreoffice-kit>fflate': '0.8.3',
  '@deepseek-ai/dsh-mcp-client>@modelcontextprotocol/client': '2.3.0',
  '@modelcontextprotocol/client>@modelcontextprotocol/core': '2.3.0',
};
const seen = new Set(), found = new Set();
const queue = [resolve(root, 'package.json')];
while (queue.length) {
  const file = queue.pop();
  if (seen.has(file)) continue;
  seen.add(file);
  const pkg = json(file);
  const dependencies = { ...pkg.peerDependencies, ...pkg.optionalDependencies, ...pkg.dependencies };
  for (const name of Object.keys(dependencies)) {
    const optional = Boolean(pkg.optionalDependencies?.[name] || pkg.peerDependenciesMeta?.[name]?.optional);
    const dep = locate(file, name, optional);
    if (!dep) continue;
    const info = json(dep);
    if (info.name !== name) throw Error(`${kind}: ${name} resolves to ${info.name} at ${dep}`);
    const key = `${pkg.name}>${name}`;
    const expected = name === 'zod' ? '4.6.6' : checks[key];
    if (expected && info.version !== expected) throw Error(`${kind}: ${key} resolved ${info.version}, expected ${expected}: ${dep}`);
    if (expected) { found.add(key); console.log(`${kind}: ${key} = ${info.version} at ${dep}`); }
    queue.push(dep);
  }
}
if (kind === 'host') for (const key of Object.keys(checks)) if (!found.has(key)) throw Error(`host: required consumer ${key} not found`);
if (kind === 'profile' && !found.has('@deepseek-ai/dsh-http-proxy>undici')) throw Error('profile: proxy consumer not found');
if (kind === 'profile' && !seen.has(realpathSync(join(root, 'node_modules', '@dsh-runtime', 'harness-plugin', 'package.json')))) throw Error('profile: plugin not reached');
console.log(`${kind}: checked ${seen.size} package manifests and root identities`);
