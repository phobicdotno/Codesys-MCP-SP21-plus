import { describe, it, expect } from 'vitest';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { buildReleaseCommitMessage, gitCommitWithMessage, mergeReleaseEvidence } from '../../src/server';

// Regression tests for two release_project_version defects seen on Lib001
// v2.0.4.0 and v2.0.5.0 (2026-09-14):
//  1. The commit was made with `-m JSON.stringify(msg)`. On Windows the shell
//     kept the JSON escapes, so the message held literal "\n" sequences, and
//     the evidence summary was cut to 5 items / 200 characters ("...; m\n").
//  2. The file list came from the pre-bump classification, so
//     _MCP_PROJECT_VERSION.st (changed by the bump itself) was never listed.

const MIRROR = 'mcp-mirror/_750_8216_PFC200/Plc Logic/Application';

describe('buildReleaseCommitMessage', () => {
  it('lists every evidence item on its own line, untruncated', () => {
    const evidence = [
      'baseline: tag v2.0.4.0',
      `modified: ${MIRROR}/Can/Can Raw/FB_Can.st`,
      `modified: ${MIRROR}/Can/Can Raw/FB_Can658Config.st`,
      `modified: ${MIRROR}/_MCP_FUNCTION_VERSIONS.st`,
      `modified: ${MIRROR}/_MCP_PROJECT_VERSION.st`,
      `modified: ${MIRROR}/Extra/Sixth.st`,
    ];
    const msg = buildReleaseCommitMessage('2.0.5.0', 'auto: revision', evidence);
    const lines = msg.split('\n');
    expect(lines[0]).toBe('release v2.0.5.0 (auto: revision)');
    expect(lines[1]).toBe('');
    expect(lines.slice(2, 8)).toEqual(evidence.map((e) => `- ${e}`));
    expect(msg).not.toContain('\\n');
  });

  it('says so when there is no evidence', () => {
    expect(buildReleaseCommitMessage('1.0.0.0', 'seed', [])).toBe('release v1.0.0.0 (seed)\n\n- (no classification evidence)\n');
  });
});

describe('mergeReleaseEvidence', () => {
  it('adds files changed by the bump, keeps order, drops duplicates', () => {
    const before = ['baseline: tag v2.0.4.0', `modified: ${MIRROR}/Can/Can Raw/FB_Can.st`];
    const after = [
      'baseline: tag v2.0.4.0',
      `modified: ${MIRROR}/Can/Can Raw/FB_Can.st`,
      `modified: ${MIRROR}/_MCP_PROJECT_VERSION.st`,
    ];
    expect(mergeReleaseEvidence(before, after)).toEqual([...before, `modified: ${MIRROR}/_MCP_PROJECT_VERSION.st`]);
  });
});

describe('gitCommitWithMessage', () => {
  it('stores real line breaks in the commit message', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'codesys-mcp-commit-test-'));
    try {
      const git = (cmd: string) => execSync(`git -C "${dir}" ${cmd}`, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
      git('init -q');
      git('config user.email test@example.invalid');
      git('config user.name Test');
      fs.writeFileSync(path.join(dir, 'a.txt'), 'x');
      git('add a.txt');
      const msg = buildReleaseCommitMessage('2.0.5.0', 'auto: revision', ['baseline: tag v2.0.4.0', `modified: ${MIRROR}/FB "quoted" name.st`]);
      gitCommitWithMessage(dir, msg);
      expect(git('log -1 --format=%s').trim()).toBe('release v2.0.5.0 (auto: revision)');
      expect(git('log -1 --format=%B')).toBe(msg + '\n');
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });
});
