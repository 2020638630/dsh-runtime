import { mkdtempSync, cpSync, readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const repo = resolve(import.meta.dirname, '..');
const source = join(repo, 'install', 'rc31');
const check = join(repo, 'scripts', 'check-rc31-graph.mjs');
const pnpm = process.platform === 'win32' ? 'pnpm.cmd' : 'pnpm';
const temporary = mkdtempSync(join(tmpdir(), 'rc31-install-'));
const run = (command, args, cwd) => execFileSync(command, args, { cwd, stdio: 'pipe', shell: process.platform === 'win32' && command === pnpm });
const digest = p => createHash('sha256').update(readFileSync(p)).digest('hex');
const verify = (template, root, kind, success = true) => {
  const result = spawnSync(process.execPath, [check, template, root, kind], { encoding: 'utf8' });
  if ((result.status === 0) !== success) throw Error(`unexpected graph result ${kind}: ${result.stderr}`);
  return result.stderr;
};
try {
  // Copying before installation models a different drive/directory and preserves
  // the Profile's ../../plugin-artifacts relative layout.
  const moved = join(temporary, 'relocated');
  cpSync(source, moved, { recursive: true });
  for (const [part, kind] of [['host', 'host'], ['profiles/template', 'profile']]) {
    const root = join(moved, part), template = join(source, part);
    const before = digest(join(root, 'pnpm-lock.yaml'));
    run(pnpm, ['install', '--frozen-lockfile', '--ignore-scripts', '--registry=https://registry.npmjs.org/'], root);
    if (digest(join(root, 'pnpm-lock.yaml')) !== before) throw Error('normal install rewrote lockfile');
    verify(template, root, kind);
    const lock = join(root, 'pnpm-lock.yaml');
    writeFileSync(lock, readFileSync(lock, 'utf8') + '\n# mismatch\n');
    if (!verify(template, root, kind, false).includes('pnpm-lock.yaml')) throw Error('lock mismatch not rejected');
    cpSync(join(template, 'pnpm-lock.yaml'), lock);
  }
  // Install an old graph in isolation, then present the new root policy and lock
  // without touching node_modules. The consumer check must still reject it.
  const old = join(temporary, 'old-host'); mkdirSync(old);
  cpSync(join(source, 'host', 'package.json'), join(old, 'package.json'));
  const policy = readFileSync(join(source, 'host', 'pnpm-workspace.yaml'), 'utf8')
    .split(/\r?\n/).filter(line => !/dsh-web-fetch-http|libreoffice-kit|dsh-mcp-client/.test(line)).join('\n');
  writeFileSync(join(old, 'pnpm-workspace.yaml'), policy);
  run(pnpm, ['install', '--ignore-scripts', '--registry=https://registry.npmjs.org/'], old);
  for (const name of ['pnpm-workspace.yaml', 'pnpm-lock.yaml']) cpSync(join(source, 'host', name), join(old, name));
  const error = verify(join(source, 'host'), old, 'host', false);
  if (!/resolved .*expected/.test(error)) throw Error(`old graph rejection was not a version failure: ${error}`);
  console.log('relocated frozen installs, lock mismatch and old graph rejection passed');
} finally { rmSync(temporary, { recursive: true, force: true }); }
