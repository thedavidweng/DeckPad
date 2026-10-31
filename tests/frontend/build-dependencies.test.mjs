import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import { rollup } from 'rollup';

const requireFromDecky = createRequire(import.meta.resolve('@decky/rollup'));
const { nodeResolve } = await import(requireFromDecky.resolve('@rollup/plugin-node-resolve'));
const { default: commonjs } = await import(requireFromDecky.resolve('@rollup/plugin-commonjs'));
const { default: deletePlugin } = await import(requireFromDecky.resolve('rollup-plugin-delete'));

test('build plugins resolve modules and remove only matching files', async () => {
  const directory = await realpath(await mkdtemp(path.join(tmpdir(), 'deckpad-build-')));
  try {
    const packageDirectory = path.join(directory, 'node_modules', 'fixture-package');
    await mkdir(packageDirectory, { recursive: true });
    await writeFile(path.join(packageDirectory, 'package.json'), JSON.stringify({ main: 'index.cjs' }));
    await writeFile(path.join(packageDirectory, 'index.cjs'), 'module.exports = require("./" + process.env.NAME + ".cjs");');
    const moduleFile = path.join(packageDirectory, 'module.cjs');
    const entryFile = path.join(directory, 'entry.mjs');
    const removeFile = path.join(directory, 'remove.tmp');
    await writeFile(moduleFile, 'module.exports = 42;');
    await writeFile(entryFile, 'import value from "fixture-package"; export default value;');
    await writeFile(removeFile, 'remove');

    const bundle = await rollup({
      input: entryFile,
      plugins: [nodeResolve(), commonjs({
        dynamicRequireRoot: directory,
        dynamicRequireTargets: [path.join(packageDirectory, 'module*.cjs')],
      })],
      onwarn(warning) { throw new Error(warning.message); },
    });
    const { output } = await bundle.generate({ format: 'cjs' });
    await bundle.close();
    const module = { exports: {} };
    runInNewContext(output[0].code, { module, exports: module.exports, process: { env: { NAME: 'module' } } });
    assert.equal(module.exports, 42);
    await deletePlugin({ targets: [path.join(directory, '*.tmp')], force: true }).buildStart();

    assert.equal(await readFile(moduleFile, 'utf8'), 'module.exports = 42;');
    await assert.rejects(readFile(removeFile), { code: 'ENOENT' });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
