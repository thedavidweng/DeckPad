import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { setImmediate } from 'node:timers/promises';
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm';
import test from 'node:test';

const ts = createRequire(import.meta.resolve('@decky/rollup'))('typescript');

async function diagnostics() {
  const calls = [], values = [], effects = [];
  const context = createContext({ console });
  const bindings = {
    react: {
      useState: initial => [initial === false ? true : initial, next => values.push(next)],
      useRef: initial => ({ current: initial }),
      useEffect: effect => effects.push(effect),
    },
    '@decky/ui': { ButtonItem: 'Button', Field: 'Field', PanelSection: 'Section', PanelSectionRow: 'Row' },
    './backend': { getDiagnostics: () => new Promise((resolve, reject) => calls.push({ resolve, reject })) },
    'react/jsx-runtime': { Fragment: 'Fragment', jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
  };
  const source = await readFile(new URL('../../src/troubleshooting.tsx', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
    fileName: 'troubleshooting.tsx',
  }).outputText;
  const module = new SourceTextModule(compiled, { context });
  await module.link(name => new SyntheticModule(Object.keys(bindings[name]), function () {
    for (const [key, value] of Object.entries(bindings[name])) this.setExport(key, value);
  }, { context }));
  await module.evaluate();
  module.namespace.Troubleshooting();
  return { calls, values, effect: effects[0] };
}

test('an older diagnostics response cannot replace a newer refresh', async () => {
  const d = await diagnostics();
  const cleanup = d.effect();
  d.effect();
  d.calls[1].resolve({ text: 'new' });
  await setImmediate();
  d.calls[0].resolve({ text: 'old' });
  await setImmediate();
  assert.deepEqual(d.values, [null, null, { text: 'new' }]);
  cleanup();
});

test('hiding diagnostics or unmounting ignores a pending failure', async () => {
  const d = await diagnostics();
  d.effect()();
  d.calls[0].reject(new Error('offline'));
  await setImmediate();
  assert.deepEqual(d.values, [null]);
});
