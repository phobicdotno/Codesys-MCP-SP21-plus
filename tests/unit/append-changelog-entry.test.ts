import { describe, it, expect } from 'vitest';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';
import { appendChangelogEntry } from '../../src/server';

// I/O-level regression test for the Changelog silent-no-op bug. Complements
// build-changelog-update.test.ts (pure logic) by exercising the real
// read-write-verify path against actual files on disk, including the exact
// filename casings observed on the two affected repos.

async function tmpDir(): Promise<string> {
  return fs.mkdtemp(path.join(os.tmpdir(), 'phobics-changelog-'));
}

describe('appendChangelogEntry (I/O)', () => {
  it('writes and verifies a fresh Changelog.md when none exists', async () => {
    const dir = await tmpDir();
    const result = appendChangelogEntry(dir, null, '1.0.0.0', 'seed', ['initial import']);
    expect(result.status).toBe('written');
    const onDisk = await fs.readFile(path.join(dir, 'Changelog.md'), 'utf-8');
    expect(onDisk).toContain('## v1.0.0.0 - ');
  });

  it('actually writes the entry to an existing Changelog.md (title-case filename)', async () => {
    const dir = await tmpDir();
    const seedPath = path.join(dir, 'Changelog.md');
    await fs.writeFile(
      seedPath,
      '# Changelog\n\n' +
        'Auto-appended by `bump_project_version` on release.\n\n' +
        '## v1.3.0.0 -- 2026-07-23\n\n- prior entry\n',
      'utf-8'
    );

    const result = appendChangelogEntry(dir, '1.3.0.0', '1.3.1.0', 'auto: revision', ['new stuff']);
    expect(result.status).toBe('written');

    const onDisk = await fs.readFile(seedPath, 'utf-8');
    expect(onDisk).toContain('## v1.3.1.0 - ');
    expect(onDisk).toContain('- new stuff');
    expect(onDisk.indexOf('v1.3.1.0')).toBeLessThan(onDisk.indexOf('v1.3.0.0'));
  });

  it('actually writes the entry when the on-disk file is uppercase CHANGELOG.md', async () => {
    const dir = await tmpDir();
    const upperPath = path.join(dir, 'CHANGELOG.md');
    await fs.writeFile(
      upperPath,
      '# Changelog\n\n' +
        'Format follows [Keep a Changelog](https://keepachangelog.com/).\n\n' +
        '## [Unreleased]\n\n' +
        '## [0.20.2.2] - 2026-07-23\n\n- prior entry\n',
      'utf-8'
    );

    const result = appendChangelogEntry(dir, '0.20.2.2', '0.21.0.0', 'auto: minor', ['21 PGN decoders added']);
    expect(result.status).toBe('written');
    expect(result.style).toBe('keepachangelog');

    // Windows filesystems are case-insensitive: reading back via either
    // casing must show the same, actually-written content.
    const viaUpper = await fs.readFile(upperPath, 'utf-8');
    const viaLower = await fs.readFile(path.join(dir, 'Changelog.md'), 'utf-8');
    expect(viaUpper).toBe(viaLower);
    expect(viaUpper).toContain('## [0.21.0.0] - ');
    expect(viaUpper).toContain('- 21 PGN decoders added');
  });

  it('reports skipped (not written) for a genuinely hand-maintained, unrecognized file', async () => {
    const dir = await tmpDir();
    await fs.writeFile(
      path.join(dir, 'Changelog.md'),
      '# Changelog\n\nHand-written prose changelog, no headings this tool understands.\n',
      'utf-8'
    );
    const before = await fs.readFile(path.join(dir, 'Changelog.md'), 'utf-8');

    const result = appendChangelogEntry(dir, null, '1.0.0.0', 'auto: revision', ['x']);
    expect(result.status).toBe('skipped');
    expect(result.reason).toBeTruthy();

    const after = await fs.readFile(path.join(dir, 'Changelog.md'), 'utf-8');
    expect(after).toBe(before);
  });
});
