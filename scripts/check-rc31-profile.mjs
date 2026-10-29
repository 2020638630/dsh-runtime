import { createRequire } from 'node:module';
import { realpathSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';

// Resolve the exact parser and dialect used by the qualified Host's app-boot.
const [runner, patch, mode = "2"] = process.argv.slice(2);
if (!runner || !patch) throw Error('Expected Host runner and Profile patch');
const hostRequire = createRequire(realpathSync(join(runner, 'node_modules/@deepseek-ai/dsh/lib/bin.js')));
const bootRequire = createRequire(hostRequire.resolve('@deepseek-ai/dsh-app-boot'));
const yaml = bootRequire('js-yaml');
const { entryListSchema } = await import(pathToFileURL(bootRequire.resolve('@deepseek-ai/cordis-plugin-include')).href);
let parsed;
try { parsed = yaml.load(readFileSync(patch, 'utf8'), { schema: entryListSchema }); } catch { throw Error('Invalid patch YAML'); }
const seen = new Set();
function canonical(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'object' || seen.has(value)) throw Error('Unsupported or shared YAML value');
  seen.add(value);
  if (Array.isArray(value)) return value.map(canonical);
  if (Object.getPrototypeOf(value) !== Object.prototype) throw Error('Unsupported YAML object');
  const result = Object.create(null);
  for (const key of Object.keys(value).sort()) result[key] = canonical(value[key]);
  return result;
}
const rows = canonical(parsed);
if (mode === 'home') {
  if (!Array.isArray(rows) || rows.length !== 0) throw Error('Home patch must be an empty list');
  process.stdout.write('EMPTY');
  process.exit(0);
}
if (mode === '3') {
  if (!Array.isArray(rows) || rows.length < 1 || rows.length > 3 || rows[0]?.id !== 'dsh-runtime-standalone') throw Error('Unexpected Profile patch entries');
  const ids = new Set();
  for (const row of rows) {
    if (!row || typeof row !== 'object' || Array.isArray(row) || typeof row.id !== 'string' || ids.has(row.id)) throw Error('Invalid or duplicate Profile entry');
    ids.add(row.id);
  }
  const exactKeys = (obj, required, optional = []) => obj && typeof obj === 'object' && !Array.isArray(obj) && required.every(k => Object.hasOwn(obj, k)) && Object.keys(obj).every(k => required.includes(k) || optional.includes(k));
  for (const row of rows.slice(1)) {
    if (!exactKeys(row, ['id', 'name', 'config'])) throw Error('Invalid mutable entry');
    if (row.id === 'ui-settings-general') {
      if (row.name !== '@deepseek-ai/dsh-client-ui-settings-general' || !exactKeys(row.config, ['welcomeNoticeVersion']) || row.config.welcomeNoticeVersion !== '2026-09-28.1') throw Error('Invalid welcome settings');
    } else if (row.id === 'agent-default-model') {
      if (row.name !== '@deepseek-ai/dsh-agent-default-model' || !exactKeys(row.config, ['provider', 'model'], ['reasoningEffort']) || typeof row.config.provider !== 'string' || typeof row.config.model !== 'string' || (Object.hasOwn(row.config, 'reasoningEffort') && typeof row.config.reasoningEffort !== 'string')) throw Error('Invalid default model settings');
    } else throw Error('Unknown Profile entry');
  }
  process.stdout.write(createHash('sha256').update(JSON.stringify([rows[0]])).digest('hex').toUpperCase());
  process.exit(0);
}
if (mode !== '2') throw Error('Unknown Profile schema');
if (!Array.isArray(rows) || rows.length < 1 || rows.length > 2 || rows[0]?.id !== 'dsh-runtime-standalone') throw Error('Unexpected Profile patch entries');
if (rows.length === 2) {
  const expected = { id: 'ui-settings-general', name: '@deepseek-ai/dsh-client-ui-settings-general', config: { welcomeNoticeVersion: '2026-09-28.1' } };
  // Canonicalize both sides so mapping order and formatting are immaterial.
  if (JSON.stringify(rows[1]) !== JSON.stringify(canonical(expected))) throw Error('Unexpected welcome settings');
  rows.pop();
}
process.stdout.write(createHash('sha256').update(JSON.stringify(rows)).digest('hex').toUpperCase());
