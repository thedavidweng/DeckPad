import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';

// Compile with the TypeScript compiler already used by the official Decky Rollup preset.
const ts = createRequire(import.meta.resolve('@decky/rollup'))('typescript');

async function screen(store) {
  const effects = [], calls = [];
  const window = { SteamUIStore: store };
  const sources = {
    react: {
      useState: value => [value, () => {}],
      useRef: value => ({ current: value }),
      useEffect: effect => effects.push(effect),
    },
    'react/jsx-runtime': {
      jsx: (type, props) => ({ type, props }),
      jsxs: (type, props) => ({ type, props }),
    },
    '@decky/ui': {
      Focusable: 'Focusable',
      GamepadButton: { STEAM_GUIDE: 12, STEAM_QUICK_MENU: 13 },
      Navigation: { NavigateBack: () => calls.push('back'), CloseSideMenus: () => calls.push('close menus') },
    },
    './backend': {
      useControllerModeState: () => ({ status: 'on', quit_combo: true, connection: 'idle', hosts: [] }),
      useGamepadPreview: () => null,
      connectedHostName: () => undefined,
      hostNames: () => new Map(),
    },
    './gamepad_outline': { GamepadOutline: () => null },
  };
  const source = await readFile(new URL('../../src/controller_screen.tsx', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
    fileName: 'controller_screen.tsx',
  }).outputText;
  const exports = {};
  const require = name => {
    assert.ok(Object.hasOwn(sources, name), `unexpected import: ${name}`);
    return sources[name];
  };
  runInNewContext(compiled, { window, console, exports, require });
  const tree = exports.ControllerScreen();
  return { window, effects, calls, tree, exports };
}

test('cleanup uses the switch that disabled menus even if SteamUIStore changes', async () => {
  const calls = [];
  const s = await screen({
    DisableHomeAndQuickAccessButtons: () => calls.push('disable'),
    EnableHomeAndQuickAccessButtons: () => calls.push('enable'),
  });
  const cleanup = s.effects[0]();
  s.window.SteamUIStore = undefined;
  cleanup();
  assert.deepEqual(calls, ['disable', 'enable']);
});

test('a partial disable failure restores menus before exposing the error', async () => {
  const calls = [];
  const s = await screen({
    DisableHomeAndQuickAccessButtons: () => { calls.push('disable'); throw new Error('disable failed'); },
    EnableHomeAndQuickAccessButtons: () => calls.push('enable'),
  });
  assert.throws(() => s.effects[0](), /disable failed/);
  assert.deepEqual(calls, ['disable', 'enable']);
});

test('touch Close restores menus synchronously before navigating', async () => {
  const calls = [];
  const s = await screen({
    DisableHomeAndQuickAccessButtons: () => calls.push('disable'),
    EnableHomeAndQuickAccessButtons: () => calls.push('enable'),
  });
  s.effects[0]();
  s.exports.closeControllerScreen();
  assert.deepEqual(calls, ['disable', 'enable']);
  assert.deepEqual(s.calls, ['back', 'close menus']);
});

test('a failed restore remains owned for another restore attempt', async () => {
  let attempts = 0;
  const s = await screen({
    DisableHomeAndQuickAccessButtons() {},
    EnableHomeAndQuickAccessButtons() { if (++attempts === 1) throw new Error('enable failed'); },
  });
  s.effects[0]();
  assert.throws(() => s.exports.restoreSteamMenus(), /enable failed/);
  s.exports.restoreSteamMenus();
  assert.equal(attempts, 2);
});

test('capturing consumes game controls and leaves Steam menu button events alone', async () => {
  const s = await screen(undefined);
  const cancelled = [];
  const event = button => ({
    detail: { button },
    preventDefault: () => cancelled.push('default'),
    stopPropagation: () => cancelled.push('propagation'),
  });
  s.tree.props.onButtonDown(event(1));
  assert.deepEqual(cancelled, ['default', 'propagation']);
  s.tree.props.onButtonDown(event(12));
  s.tree.props.onButtonDown(event(13));
  assert.equal(cancelled.length, 2);
});

async function plugin(overrides) {
  const source = await readFile(new URL('../../src/index.tsx', import.meta.url), 'utf8');
  const ast = ts.createSourceFile('index.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const imports = new Map(ast.statements.filter(ts.isImportDeclaration).map(node => [
    node.moduleSpecifier.text, node.importClause.namedBindings.elements.map(binding => binding.propertyName?.text ?? binding.name.text),
  ]));
  const bindings = {
    definePlugin: factory => factory,
    routerHook: { addRoute() {}, removeRoute() {} },
    CONTROLLER_SCREEN_ROUTE: '/deckpad/controller',
    restoreSteamMenus: () => { throw new Error('enable failed'); },
    jsx: () => null,
    jsxs: () => null,
    ...overrides,
  };
  imports.set('react/jsx-runtime', ['jsx', 'jsxs', 'Fragment']);
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
    fileName: 'index.tsx',
  }).outputText;
  const exports = {};
  const require = name => Object.fromEntries(imports.get(name).map(key => [key, bindings[key] ?? (() => null)]));
  runInNewContext(compiled, { console, exports, require });
  return exports.default();
}

test('dismount removes the route even when Steam refuses restoration', async () => {
  const removed = [];
  const p = await plugin({
    routerHook: { addRoute() {}, removeRoute: route => removed.push(route) },
  });
  assert.throws(() => p.onDismount(), /enable failed/);
  assert.deepEqual(removed, ['/deckpad/controller']);
});


test('every QAM action clears an old request error before sending a new request', async () => {
  const values = [], calls = [];
  const state = {
    status: 'on', connection: 'paused', hosts: [], quit_combo: true,
    pairing: { status: 'closed', seconds_left: null },
  };
  const jsx = (type, props) => ({ type, props });
  const p = await plugin({
    jsx, jsxs: jsx,
    useControllerModeState: () => state,
    useControllerScreenOpen: () => false,
    useState: value => [value, next => values.push(next)],
    hostNames: () => new Map(),
    setControllerMode: async () => { throw new Error('offline'); },
    allowReconnect: async () => calls.push('reconnect'),
    setPairingMode: async () => calls.push('pair'),
    setQuitCombo: async () => calls.push('setting'),
  });
  const content = p.content.type();
  const nodes = [];
  function visit(node) {
    if (!node?.props) return;
    nodes.push(node);
    for (const child of [node.props.children].flat()) visit(child);
  }
  visit(content);
  const toggle = nodes.find(node => node.props.label === 'Controller Mode');
  await toggle.props.onChange(false);
  assert.equal(values.at(-1), "Reload DeckPad from Decky's settings, then try again.");
  const connection = nodes.find(node => node.props.state && node.props.screenOpen === false);
  const pairing = nodes.find(node => node.props.pairing);
  const quit = nodes.find(node => node.props.label === 'Quit Combo');
  for (const component of [connection, pairing]) {
    nodes.length = 0;
    visit(component.type(component.props));
    await nodes.find(node => node.props.onClick).props.onClick();
  }
  await quit.props.onChange(false);
  assert.deepEqual(calls, ['reconnect', 'pair', 'setting']);
  assert.deepEqual(values.slice(-3), [null, null, null]);
});
