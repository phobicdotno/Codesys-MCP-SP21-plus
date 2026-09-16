/**
 * Run a vitest test file WITHOUT vitest.
 *
 * vitest hangs indefinitely on some Windows/Node combinations (observed with
 * Node 24: every test file, including untouched ones, never starts). This
 * runner transpiles a .test.ts with the esbuild already in node_modules,
 * injects minimal describe/it/expect shims, and executes it, so the real test
 * file stays the single source of truth instead of a hand-copied mirror.
 *
 * Usage: node tests/run-without-vitest.mjs tests/integration/<file>.test.ts
 * Only the matcher subset used by these tests is implemented; an unsupported
 * matcher throws rather than silently passing.
 */
import * as esbuild from 'esbuild';
import * as path from 'path';
import * as url from 'url';
import * as fs from 'fs';
import * as os from 'os';

const repoRoot = path.resolve(path.dirname(url.fileURLToPath(import.meta.url)), '..');
// Leftovers from a killed run (the bundle is removed on a normal exit).
for (const f of fs.readdirSync(path.join(repoRoot, 'node_modules'))) {
  if (f.startsWith('.test-bundle-')) { try { fs.unlinkSync(path.join(repoRoot, 'node_modules', f)); } catch { /* ignore */ } }
}

const target = process.argv[2];
if (!target) {
  // No argument: run every test file in a child process each, and total up.
  const { spawnSync } = await import('node:child_process');
  const files = [];
  for (const dir of ['unit', 'integration']) {
    const d = path.join(repoRoot, 'tests', dir);
    if (!fs.existsSync(d)) continue;
    for (const f of fs.readdirSync(d)) if (f.endsWith('.test.ts')) files.push(path.join('tests', dir, f));
  }
  let passed = 0, failed = 0;
  const bad = [];
  for (const f of files) {
    const r = spawnSync(process.execPath, [url.fileURLToPath(import.meta.url), f], { encoding: 'utf-8' });
    const m = (r.stdout || '').match(/^(\d+) passed, (\d+) failed/m);
    if (!m) { bad.push(`${f} (runner error)`); console.log(`${f.padEnd(55)} RUNNER ERROR`); continue; }
    passed += Number(m[1]); failed += Number(m[2]);
    console.log(`${f.padEnd(55)} ${m[1]} passed, ${m[2]} failed`);
    if (Number(m[2]) > 0) bad.push(f);
  }
  console.log(`\nTOTAL: ${passed} passed, ${failed} failed`);
  if (bad.length) console.log('failing files: ' + bad.join(', '));
  process.exit(failed || bad.length ? 1 : 0);
}

const shimPath = path.join(os.tmpdir(), `vitest-shim-${process.pid}.cjs`);
fs.writeFileSync(shimPath, `
const state = { suites: [], passed: 0, failed: 0, failures: [] };
globalThis.__testState = state;

function fail(message) { throw new Error(message); }
function fmt(v) { try { return JSON.stringify(v); } catch { return String(v); } }

function expect(actual) {
  const matchers = {
    toContain(sub) {
      if (typeof actual === 'string') {
        if (!actual.includes(sub)) fail('expected string to contain: ' + sub);
      } else if (Array.isArray(actual)) {
        if (!actual.includes(sub)) fail('expected array to contain: ' + fmt(sub));
      } else fail('toContain on unsupported type ' + typeof actual);
    },
    toBe(expected) { if (actual !== expected) fail('expected ' + fmt(actual) + ' to be ' + fmt(expected)); },
    toEqual(expected) {
      // Structural, order-insensitive (JSON text comparison would fail on key order).
      try { require('node:assert').deepStrictEqual(actual, expected); }
      catch { fail('expected ' + fmt(actual) + ' to equal ' + fmt(expected)); }
    },
    toBeGreaterThan(n) { if (!(actual > n)) fail('expected ' + fmt(actual) + ' > ' + fmt(n)); },
    toBeGreaterThanOrEqual(n) { if (!(actual >= n)) fail('expected ' + fmt(actual) + ' >= ' + fmt(n)); },
    toBeLessThan(n) { if (!(actual < n)) fail('expected ' + fmt(actual) + ' < ' + fmt(n)); },
    toBeLessThanOrEqual(n) { if (!(actual <= n)) fail('expected ' + fmt(actual) + ' <= ' + fmt(n)); },
    toMatch(re) { if (typeof re === 'string' ? !String(actual).includes(re) : !re.test(actual)) fail('expected ' + fmt(actual) + ' to match ' + re); },
    toBeNull() { if (actual !== null) fail('expected null, got ' + fmt(actual)); },
    toBeUndefined() { if (actual !== undefined) fail('expected undefined, got ' + fmt(actual)); },
    toBeDefined() { if (actual === undefined) fail('expected defined'); },
    toBeTruthy() { if (!actual) fail('expected truthy, got ' + fmt(actual)); },
    toBeFalsy() { if (actual) fail('expected falsy, got ' + fmt(actual)); },
    toHaveLength(n) { if (!actual || actual.length !== n) fail('expected length ' + n + ', got ' + (actual && actual.length)); },
    toBeInstanceOf(C) { if (!(actual instanceof C)) fail('expected instance of ' + C.name); },
    toMatchObject(expected) {
      const check = (a, e, p) => {
        for (const k of Object.keys(e)) {
          const at = a ? a[k] : undefined, et = e[k];
          if (et && typeof et === 'object' && !Array.isArray(et)) check(at, et, p + k + '.');
          else if (fmt(at) !== fmt(et)) fail('property ' + p + k + ': expected ' + fmt(et) + ', got ' + fmt(at));
        }
      };
      check(actual, expected, '');
    },
    toThrow(expected) {
      let threw = false, msg = '';
      try { actual(); } catch (e) { threw = true; msg = e && e.message ? e.message : String(e); }
      if (!threw) fail('expected function to throw');
      if (expected) {
        const ok = typeof expected === 'string' ? msg.includes(expected) : expected.test(msg);
        if (!ok) fail('expected throw matching ' + fmt(expected) + ', got: ' + msg);
      }
    },
    get not() {
      return {
        toContain(sub) { if (String(actual).includes(sub)) fail('expected NOT to contain: ' + sub); },
        toMatch(re) { if (typeof re === 'string' ? String(actual).includes(re) : re.test(actual)) fail('expected NOT to match ' + re); },
        toBe(expected) { if (actual === expected) fail('expected not to be ' + fmt(expected)); },
        toBeNull() { if (actual === null) fail('expected not null'); },
        toBeUndefined() { if (actual === undefined) fail('expected not undefined'); },
        toThrow() { try { actual(); } catch (e) { fail('expected no throw, got: ' + (e && e.message ? e.message : String(e))); } },
        toEqual(expected) {
          let same = true;
          try { require('node:assert').deepStrictEqual(actual, expected); } catch { same = false; }
          if (same) fail('expected not to equal ' + fmt(expected));
        },
      };
    },
  };
  return new Proxy(matchers, {
    get(t, prop) {
      if (prop in t) return t[prop];
      throw new Error('run-without-vitest: matcher "' + String(prop) + '" is not implemented');
    },
  });
}
// Suites collect their tests first, then run them, so that beforeEach/afterEach
// fire around EVERY test the way vitest does (running them inline instead
// breaks any suite that builds a temp dir per test).
const stack = [];
const current = () => stack[stack.length - 1];

function describe(name, fn) {
  const suite = { name, tests: [], beforeAll: [], afterAll: [], beforeEach: [], afterEach: [] };
  stack.push(suite);
  try { fn(); } finally { stack.pop(); }
  state.suites.push(name);
  console.log('\\n' + name);
  const outer = stack.map((s) => s).reverse();
  const before = [].concat(...outer.map((s) => s.beforeEach), suite.beforeEach);
  const after = [].concat(suite.afterEach, ...outer.map((s) => s.afterEach));
  for (const h of suite.beforeAll) runHook(h, 'beforeAll');
  for (const t of suite.tests) {
    try {
      for (const h of before) h();
      t.fn();
      state.passed++;
      console.log('  PASS ' + t.name);
    } catch (e) {
      state.failed++;
      state.failures.push(t.name + ': ' + e.message);
      console.log('  FAIL ' + t.name + '\\n        ' + e.message);
    } finally {
      for (const h of after) runHook(h, 'afterEach');
    }
  }
  for (const h of suite.afterAll) runHook(h, 'afterAll');
}

function runHook(h, label) { try { h(); } catch (e) { console.log('  HOOK ERROR (' + label + ') ' + e.message); } }

function it(name, fn) {
  const suite = current();
  if (!suite) { // test outside any describe
    try { fn(); state.passed++; console.log('  PASS ' + name); }
    catch (e) { state.failed++; state.failures.push(name + ': ' + e.message); console.log('  FAIL ' + name + '\\n        ' + e.message); }
    return;
  }
  suite.tests.push({ name, fn });
}

const hook = (kind) => (fn) => { const s = current(); if (s) s[kind].push(fn); else runHook(fn, kind); };
module.exports = {
  describe, it, test: it, expect,
  beforeAll: hook('beforeAll'), afterAll: hook('afterAll'),
  beforeEach: hook('beforeEach'), afterEach: hook('afterEach'),
};
`);

const aliasPlugin = {
  name: 'alias',
  setup(build) {
    build.onResolve({ filter: /^vitest$/ }, () => ({ path: shimPath }));
    // Use the compiled output for src imports so this runner needs no TS build of its own.
    build.onResolve({ filter: /src\/(server|script-manager)$/ }, (args) => {
      const name = args.path.endsWith('server') ? 'server.js' : 'script-manager.js';
      return { path: path.join(repoRoot, 'dist', name) };
    });
  },
};

// Inside the repo so that `packages: 'external'` still resolves node_modules.
const out = path.join(repoRoot, 'node_modules', `.test-bundle-${process.pid}.cjs`);
await esbuild.build({
  entryPoints: [path.resolve(target)],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  packages: 'external',
  outfile: out,
  plugins: [aliasPlugin],
  logLevel: 'error',
  // The bundle lives elsewhere, so keep __dirname pointing at the test file.
  define: {
    __dirname: JSON.stringify(path.dirname(path.resolve(target))),
    __filename: JSON.stringify(path.resolve(target)),
  },
});

const { createRequire } = await import('node:module');
createRequire(import.meta.url)(out);
const state = globalThis.__testState;
console.log(`\n${state.passed} passed, ${state.failed} failed`);
for (const f of state.failures) console.log('  - ' + f);
for (const p of [shimPath, out]) { try { fs.unlinkSync(p); } catch { /* best effort */ } }
process.exit(state.failed ? 1 : 0);
