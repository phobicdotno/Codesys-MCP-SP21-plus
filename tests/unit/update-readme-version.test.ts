import { describe, it, expect } from 'vitest';
import { updateReadmeVersion } from '../../src/server';

// Regression test for the release_project_version README bug (2026-07-23,
// SeaLeopard v1.3.0.0 -> v1.3.1.0): the old implementation was a blanket
// `content.replace(/v\d+\.\d+\.\d+\.\d+/g, ...)` that rewrote EVERY
// version-looking string in the file, corrupting historical references and
// even a different project's (Lib001) version. This fixture carries all
// five decoy strings observed in the real README plus the real title.

const SEA_LEOPARD_README_FIXTURE = `# Sea Leopard — MRCodesysSeaLeopard_BZM_00 — v1.3.0.0

Maritime Robotics **Sea Leopard (BZM120)** vessel CODESYS PLC project. Its NMEA 2000 / CAN
library is synced to **nmea2000-mr-library (Lib001) v0.21.0.0** (see \`Changelog.md\`).

## TODO / remaining

- [ ] **STW-01 -- power-cycle-verify the \`FB_Can\` K-bus cold-boot fix (v1.2.1.0)** on a real
      750-658.

## Layout

- \`MRLib/Can\` -- the synced NMEA 2000 / CAN library (Lib001 v0.21.0.0): raw CAN transport.
- The old bespoke CAN wrappers were removed in v1.2.0.0 -- the N2k device decoders now come
  solely from the synced \`MRLib/Can\` library.

## Build archive

The last Drive copy backup has \`..._BZM_03.project\` = v1.2.0.0 and \`..._BZM_004.project\` =
v1.2.1.0 (the STW-01 RC fix) -- so the next Drive copy is due.
`;

describe('updateReadmeVersion', () => {
  it('only rewrites the title heading, leaving all decoy version strings untouched', () => {
    const result = updateReadmeVersion(SEA_LEOPARD_README_FIXTURE, '1.3.1.0');

    expect(result.changed).toBe(true);
    const lines = result.content.split('\n');
    expect(lines[0]).toBe('# Sea Leopard — MRCodesysSeaLeopard_BZM_00 — v1.3.1.0');

    // All five decoys must survive byte-for-byte.
    expect(result.content).toContain('**nmea2000-mr-library (Lib001) v0.21.0.0**');
    expect(result.content).toContain('the synced NMEA 2000 / CAN library (Lib001 v0.21.0.0)') ;
    expect(result.content).toContain('MRLib/Can\` -- the synced NMEA 2000 / CAN library (Lib001 v0.21.0.0)');
    expect(result.content).toContain('power-cycle-verify the `FB_Can` K-bus cold-boot fix (v1.2.1.0)');
    expect(result.content).toContain('The old bespoke CAN wrappers were removed in v1.2.0.0');
    expect(result.content).toContain('`..._BZM_03.project` = v1.2.0.0 and `..._BZM_004.project` =\nv1.2.1.0');

    // Only the title line should differ from the fixture.
    const fixtureLines = SEA_LEOPARD_README_FIXTURE.split('\n');
    let changedLines = 0;
    for (let i = 0; i < fixtureLines.length; i++) {
      if (fixtureLines[i] !== lines[i]) changedLines++;
    }
    expect(changedLines).toBe(1);
  });

  it('is a no-op when the title is already at the target version', () => {
    const already = SEA_LEOPARD_README_FIXTURE.replace('v1.3.0.0', 'v1.3.1.0');
    const result = updateReadmeVersion(already, '1.3.1.0');
    expect(result.changed).toBe(false);
    expect(result.content).toBe(already);
  });

  it('handles the Lib001 "**Version:**" convention (bare number, no v prefix)', () => {
    const lib001Fixture =
      '# MR Library Lib001\n\n' +
      'Maritime Robotics CAN / NMEA 2000 library.\n\n' +
      '**Version:** `0.19.0.0`\n\n' +
      '## Hardware / runtime\n';
    const result = updateReadmeVersion(lib001Fixture, '0.21.0.0');
    expect(result.changed).toBe(true);
    expect(result.content).toContain('**Version:** `0.21.0.0`');
    expect(result.content).not.toContain('0.19.0.0');
  });

  it('changes nothing and reports clearly when no anchor is found', () => {
    const noAnchor = '# Just a title\n\nNo version reference anywhere in this file.\n';
    const result = updateReadmeVersion(noAnchor, '1.0.0.0');
    expect(result.changed).toBe(false);
    expect(result.content).toBe(noAnchor);
    expect(result.detail).toMatch(/no recognized version anchor/i);
  });

  it('changes nothing when the "**Version:**" anchor is ambiguous (more than one match)', () => {
    const ambiguous =
      '# Title\n\n**Version:** `1.0.0.0`\n\nSomewhere else:\n\n**Version:** `1.0.0.0`\n';
    const result = updateReadmeVersion(ambiguous, '2.0.0.0');
    expect(result.changed).toBe(false);
    expect(result.detail).toMatch(/ambiguous/i);
  });

  it('never falls back to a global replace even when the title anchor is missing a version token', () => {
    const noTitleVersion =
      '# Sea Leopard\n\nSynced to Lib001 v0.21.0.0.\n\nHistorical fix in v1.2.1.0.\n';
    const result = updateReadmeVersion(noTitleVersion, '1.3.1.0');
    expect(result.changed).toBe(false);
    expect(result.content).toBe(noTitleVersion);
  });
});
