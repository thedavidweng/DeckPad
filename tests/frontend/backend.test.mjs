import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import { setImmediate } from 'node:timers/promises';
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm';
import test from 'node:test';

// Exercise the actual hook effects; React and Decky are the external interfaces under test.
async function backend() {
  const effects = [], values = [], calls = [], listeners = new Map();
  const api = {
    callable: route => (...args) => new Promise((resolve, reject) => calls.push({ route, args, resolve, reject })),
    addEventListener: (event, listener) => {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event).add(listener);
      return listener;
    },
    removeEventListener: (event, listener) => listeners.get(event).delete(listener),
  };
  const react = {
    useState: () => [null, value => values.push(value)],
    useEffect: effect => effects.push(effect),
  };
  const context = createContext({ console });
  const source = stripTypeScriptTypes(await readFile(new URL('../../src/backend.ts', import.meta.url), 'utf8'));
  const module = new SourceTextModule(source, { context });
  await module.link(name => {
    const exports = name === 'react' ? react : api;
    return new SyntheticModule(Object.keys(exports), function () {
      for (const [name, value] of Object.entries(exports)) this.setExport(name, value);
    }, { context });
  });
  await module.evaluate();
  return {
    values, calls, listeners,
    mount(name, ...args) {
      module.namespace[name](...args);
      return effects.shift()();
    },
    emit(event, value) {
      for (const listener of listeners.get(event)) listener(value);
    },
  };
}

const stateEvent = 'controller_mode_state';

test('live events win over an older initial query', async () => {
  const b = await backend();
  const unmount = b.mount('useControllerModeState');
  b.emit(stateEvent, { status: 'on' });
  b.calls[0].resolve({ status: 'off' });
  await setImmediate();
  assert.deepEqual(b.values, [{ status: 'on' }]);
  unmount();
  assert.equal(b.listeners.get(stateEvent).size, 0);
});

test('late queries after unmount cannot update state', async () => {
  const b = await backend();
  b.mount('useControllerModeState')();
  b.calls[0].resolve({ status: 'on' });
  await setImmediate();
  assert.deepEqual(b.values, []);
});

test('an older failed query cannot clear a live event', async () => {
  const b = await backend();
  const unmount = b.mount('useControllerModeState');
  b.emit(stateEvent, { status: 'on' });
  b.calls[0].reject(new Error('backend unavailable'));
  await setImmediate();
  assert.deepEqual(b.values, [{ status: 'on' }]);
  unmount();
});

test('preview ownership lasts until the last screen unsubscribes', async () => {
  const b = await backend();
  const first = b.mount('useGamepadPreview', true);
  const second = b.mount('useGamepadPreview', true);
  await setImmediate();
  assert.equal(b.calls.length, 1);
  assert.deepEqual(b.calls[0].args, [true]);
  b.calls[0].resolve();
  await setImmediate();
  first();
  await setImmediate();
  assert.equal(b.calls.length, 1);
  second();
  await setImmediate();
  assert.deepEqual(b.calls[1].args, [false]);
  b.calls[1].resolve();
  assert.equal(b.listeners.get('gamepad_report').size, 0);
});

test('a delayed old unsubscribe finishes before a new subscribe', async () => {
  const b = await backend();
  b.mount('useGamepadPreview', true)();
  const newest = b.mount('useGamepadPreview', true);
  await setImmediate();
  assert.equal(b.calls.length, 1);
  for (const enabled of [true, false, true]) {
    const call = b.calls.at(-1);
    assert.deepEqual(call.args, [enabled]);
    call.resolve();
    await setImmediate();
  }
  newest();
  await setImmediate();
  assert.deepEqual(b.calls.at(-1).args, [false]);
  b.calls.at(-1).resolve();
});
