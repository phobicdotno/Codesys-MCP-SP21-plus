import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import {
  parseProfileVersion,
  parseProfileLabel,
  parsePinText,
  parseLibraryMdProfile,
  resolveVersionPin,
  decideVersionPin,
  label,
} from '../../src/version-pin';

describe('parseProfileVersion', () => {
  it('maps rawPatch/10 to the install-dir patch convention', () => {
    expect(parseProfileVersion('3.5.19.20')).toEqual({ sp: 19, patch: 2 });
    expect(parseProfileVersion('3.5.21.50')).toEqual({ sp: 21, patch: 5 });
    expect(parseProfileVersion('3.5.22.10')).toEqual({ sp: 22, patch: 1 });
  });

  it('treats a zero raw patch as patch 0', () => {
    expect(parseProfileVersion('3.5.18.0')).toEqual({ sp: 18, patch: 0 });
  });

  it('returns undefined for non-version text', () => {
    expect(parseProfileVersion('CODESYS V3.5 SP19')).toBeUndefined();
  });
});

describe('parseProfileLabel', () => {
  it('parses SP with and without a patch', () => {
    expect(parseProfileLabel('CODESYS V3.5 SP21 Patch 5')).toEqual({ sp: 21, patch: 5 });
    expect(parseProfileLabel('CODESYS V3.5 SP19')).toEqual({ sp: 19, patch: 0 });
  });

  it('returns undefined when there is no SP token', () => {
    expect(parseProfileLabel('3.5.19.20')).toBeUndefined();
  });
});

describe('parsePinText', () => {
  it('accepts either form', () => {
    expect(parsePinText('3.5.19.20')).toEqual({ sp: 19, patch: 2 });
    expect(parsePinText('CODESYS V3.5 SP19')).toEqual({ sp: 19, patch: 0 });
  });

  it('prefers the dotted version when a line carries both', () => {
    expect(parsePinText('CODESYS V3.5 SP21 Patch 5 (3.5.21.50)')).toEqual({ sp: 21, patch: 5 });
  });
});

describe('parseLibraryMdProfile', () => {
  const row =
    '| CODESYS Development System | `CODESYS.exe CODESYS V3.5 SP21 Patch 5, ScriptEngine.plugin 4.2.0.0` |';

  it('reads the SP/patch out of the generated table row', () => {
    expect(parseLibraryMdProfile(`# Library inventory\n\n${row}\n`)).toEqual({ sp: 21, patch: 5 });
  });

  it('does not mistake the ScriptEngine version for a profile version', () => {
    // Regression: a naive parseProfileVersion on this row matches "4.2.0.0".
    expect(parseLibraryMdProfile(row)).toEqual({ sp: 21, patch: 5 });
  });

  it('returns undefined when the row is absent', () => {
    expect(parseLibraryMdProfile('| Project Information.Version | `1.0.0.0` |')).toBeUndefined();
  });
});

describe('resolveVersionPin', () => {
  let dir: string;
  let proj: string;

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'version-pin-'));
    proj = path.join(dir, 'Thing.project');
    fs.writeFileSync(proj, 'not-a-zip');
  });

  afterEach(() => {
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it('returns undefined when neither source exists', () => {
    expect(resolveVersionPin(proj)).toBeUndefined();
  });

  it('reads library.md when no pin file is present', () => {
    fs.writeFileSync(
      path.join(dir, 'library.md'),
      '| CODESYS Development System | `CODESYS.exe CODESYS V3.5 SP22 Patch 1` |'
    );
    expect(resolveVersionPin(proj)).toMatchObject({ sp: 22, patch: 1, source: 'library.md' });
  });

  it('prefers .codesys-version over library.md', () => {
    fs.writeFileSync(
      path.join(dir, 'library.md'),
      '| CODESYS Development System | `CODESYS.exe CODESYS V3.5 SP22 Patch 1` |'
    );
    fs.writeFileSync(path.join(dir, '.codesys-version'), '3.5.19.20\n');
    expect(resolveVersionPin(proj)).toMatchObject({ sp: 19, patch: 2, source: '.codesys-version' });
  });

  it('skips comments and blank lines in the pin file', () => {
    fs.writeFileSync(
      path.join(dir, '.codesys-version'),
      '# authored on the MarinerX house standard\n\n3.5.19.20\n'
    );
    expect(resolveVersionPin(proj)).toMatchObject({ sp: 19, patch: 2 });
  });

  it('falls through to library.md when the pin file is unparseable', () => {
    fs.writeFileSync(path.join(dir, '.codesys-version'), 'whatever\n');
    fs.writeFileSync(
      path.join(dir, 'library.md'),
      '| CODESYS Development System | `CODESYS.exe CODESYS V3.5 SP22 Patch 1` |'
    );
    expect(resolveVersionPin(proj)).toMatchObject({ sp: 22, patch: 1, source: 'library.md' });
  });
});

describe('decideVersionPin', () => {
  const projectFilePath = 'C:\\plc\\Thing\\Thing.project';
  const pin = (sp: number, patch: number) =>
    ({ sp, patch, source: '.codesys-version' as const, raw: `3.5.${sp}.${patch * 10}` });

  it('proceeds on an exact match', () => {
    expect(
      decideVersionPin(pin(19, 2), { sp: 19, patch: 2 }, { saves: true, projectFilePath })
    ).toEqual({ action: 'proceed' });
  });

  it('refuses a saving tool when the server is newer', () => {
    const d = decideVersionPin(pin(19, 2), { sp: 21, patch: 5 }, { saves: true, projectFilePath });
    expect(d.action).toBe('refuse');
    expect(d.action === 'refuse' && d.message).toContain('UPGRADE');
  });

  it('refuses a saving tool when the server is older', () => {
    const d = decideVersionPin(pin(22, 1), { sp: 21, patch: 5 }, { saves: true, projectFilePath });
    expect(d.action).toBe('refuse');
    expect(d.action === 'refuse' && d.message).toContain('DOWNGRADE');
  });

  it('treats a patch-level difference as a mismatch too', () => {
    // The MarinerX7 failure was an SP difference, but SP21 P5 -> SP21 P2 also
    // rewrites the file; nothing here should special-case same-SP.
    const d = decideVersionPin(pin(21, 2), { sp: 21, patch: 5 }, { saves: true, projectFilePath });
    expect(d.action).toBe('refuse');
  });

  it('only warns a read-only tool on mismatch', () => {
    const d = decideVersionPin(pin(19, 2), { sp: 21, patch: 5 }, { saves: false, projectFilePath });
    expect(d.action).toBe('proceed-with-warning');
    expect(d.action === 'proceed-with-warning' && d.message).toContain('do NOT run a release');
  });

  it('refuses a saving tool when no pin is available', () => {
    const d = decideVersionPin(undefined, { sp: 21, patch: 5 }, { saves: true, projectFilePath });
    expect(d.action).toBe('refuse');
    expect(d.action === 'refuse' && d.message).toContain('.codesys-version');
  });

  it('lets an unpinned read-only tool through, so existing repos keep working', () => {
    expect(
      decideVersionPin(undefined, { sp: 21, patch: 5 }, { saves: false, projectFilePath })
    ).toEqual({ action: 'proceed' });
  });

  it('honours an explicit allowVersionUpgrade override', () => {
    expect(
      decideVersionPin(pin(19, 2), { sp: 21, patch: 5 }, {
        saves: true,
        allowUpgrade: true,
        projectFilePath,
      })
    ).toEqual({ action: 'proceed' });
  });

  it('stays out of the way when the server profile cannot be parsed', () => {
    expect(
      decideVersionPin(pin(19, 2), undefined, { saves: true, projectFilePath })
    ).toEqual({ action: 'proceed' });
  });
});

describe('label', () => {
  it('omits "Patch 0"', () => {
    expect(label({ sp: 19, patch: 0 })).toBe('CODESYS V3.5 SP19');
    expect(label({ sp: 21, patch: 5 })).toBe('CODESYS V3.5 SP21 Patch 5');
  });
});
