import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';

const requireFromDecky = createRequire(import.meta.resolve('@decky/rollup'));
const { nodeResolve } = await import(requireFromDecky.resolve('@rollup/plugin-node-resolve'));
const { default: commonjs } = await import(requireFromDecky.resolve('@rollup/plugin-commonjs'));
const { default: deletePlugin } = await import(requireFromDecky.resolve('rollup-plugin-delete'));

test('build plugins resolve modules and remove only matching files', async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'deckpad-build-'));
  try {
    const moduleFile = path.join(directory, 'module.cjs');
    const removeFile = path.join(directory, 'remove.tmp');
    await writeFile(moduleFile, 'module.exports = 1;');
    await writeFile(removeFile, 'remove');

    assert.equal(nodeResolve().name, 'node-resolve');
    assert.equal(commonjs({ dynamicRequireTargets: [path.join(directory, '*.cjs')] }).name, 'commonjs');
    await deletePlugin({ targets: [path.join(directory, '*.tmp')], force: true }).buildStart();

    assert.equal(await readFile(moduleFile, 'utf8'), 'module.exports = 1;');
    await assert.rejects(readFile(removeFile), { code: 'ENOENT' });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
