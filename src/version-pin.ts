/**
 * Repo-side CODESYS version pin.
 *
 * WHY: `src/inspect.ts` reads a project's authored CODESYS version out of
 * `projectinspectiondata.auxiliary` inside the .project ZIP. That works for
 * `.projectarchive` files -- but a plain `.project` is NOT a ZIP. Verified
 * 2026-07-24 against three projects spanning 3.5.19.20 .. 3.5.22.10: all
 * begin with magic `23 89 ED 33`, `unzip -l` fails on all of them, and no
 * plaintext profile string survives the container's compression.
 *
 * Consequence: `inspectProjectFile` throws for real projects, the
 * `open_project` pre-flight swallows the throw and proceeds, and a server
 * bound to a NEWER CODESYS silently converts the project on the next save.
 * That is how MarinerX7's v1.0.0.0 got cut on SP21 Patch 5 from a 3.5.19.20
 * project: 4,639,776 B -> 4,688,496 B, and the tagged binary stopped being
 * the software that is on the ship.
 *
 * Since the version cannot be recovered from the file, it has to come from
 * the repo. Two sources, most-specific first:
 *
 *   1. `.codesys-version` next to the .project -- one line, either a profile
 *      version (`3.5.19.20`) or a profile name (`CODESYS V3.5 SP19`). This is
 *      the human-supplied pin, and the only option when seeding a project
 *      that has no release history yet.
 *   2. The `CODESYS Development System` row of a previously generated
 *      `library.md` -- records which IDE last touched the project, so every
 *      project gets a pin for free after its first release.
 *
 * Policy is deliberately asymmetric (see `decideVersionPin`): a mismatch
 * REFUSES tools that save, and only WARNS on tools that merely read. An
 * unknown version warns rather than refusing, so existing repos keep working
 * until they are pinned.
 */

import * as fs from 'fs';
import * as path from 'path';

export interface VersionPin {
  sp: number;
  patch: number;
  /** Where the pin came from, for the operator-facing message. */
  source: '.codesys-version' | 'library.md';
  /** Verbatim text the pin was parsed from. */
  raw: string;
}

export interface PinnedProfile {
  sp: number;
  patch: number;
}

export type PinDecision =
  | { action: 'proceed' }
  | { action: 'proceed-with-warning'; message: string }
  | { action: 'refuse'; message: string };

const PIN_FILE = '.codesys-version';

/** `3.5.19.20` -> { sp: 19, patch: 2 }. rawPatch/10 matches install-dir convention. */
export function parseProfileVersion(text: string): PinnedProfile | undefined {
  const m = /(\d+)\.(\d+)\.(\d+)\.(\d+)/.exec(text);
  if (!m) return undefined;
  return { sp: parseInt(m[3], 10), patch: Math.floor(parseInt(m[4], 10) / 10) };
}

/** `CODESYS V3.5 SP21 Patch 5` -> { sp: 21, patch: 5 }. Patch defaults to 0. */
export function parseProfileLabel(text: string): PinnedProfile | undefined {
  const m = /SP(\d+)(?:\s+Patch\s+(\d+))?/i.exec(text);
  if (!m) return undefined;
  return { sp: parseInt(m[1], 10), patch: m[2] ? parseInt(m[2], 10) : 0 };
}

/**
 * Either form, version first -- `3.5.21.50` and `SP21 Patch 5` describe the
 * same install, but a line carrying both should be read as the version.
 */
export function parsePinText(text: string): PinnedProfile | undefined {
  return parseProfileVersion(text) ?? parseProfileLabel(text);
}

/**
 * Pulls the profile out of library.md's version table. The row looks like:
 *
 *   | CODESYS Development System | `CODESYS.exe CODESYS V3.5 SP21 Patch 5, ScriptEngine.plugin 4.2.0.0` |
 *
 * Only the SP/Patch label is meaningful here -- the row carries no dotted
 * profile version -- so this deliberately does not fall back to
 * `parseProfileVersion`, which would otherwise match `3.5` or the
 * ScriptEngine's `4.2.0.0`.
 */
export function parseLibraryMdProfile(markdown: string): PinnedProfile | undefined {
  for (const line of markdown.split(/\r?\n/)) {
    if (!/CODESYS Development System/i.test(line)) continue;
    return parseProfileLabel(line);
  }
  return undefined;
}

/** Reads whichever pin is available for the project, most-specific first. */
export function resolveVersionPin(projectFilePath: string): VersionPin | undefined {
  const dir = path.dirname(projectFilePath);

  const pinPath = path.join(dir, PIN_FILE);
  if (fs.existsSync(pinPath)) {
    try {
      const raw = fs.readFileSync(pinPath, 'utf8');
      // First non-empty, non-comment line.
      const line = raw
        .split(/\r?\n/)
        .map((l) => l.trim())
        .find((l) => l.length > 0 && !l.startsWith('#'));
      const parsed = line ? parsePinText(line) : undefined;
      if (parsed && line) {
        return { ...parsed, source: PIN_FILE, raw: line };
      }
    } catch {
      // Unreadable pin file falls through to library.md.
    }
  }

  const libPath = path.join(dir, 'library.md');
  if (fs.existsSync(libPath)) {
    try {
      const md = fs.readFileSync(libPath, 'utf8');
      const parsed = parseLibraryMdProfile(md);
      if (parsed) {
        return { ...parsed, source: 'library.md', raw: label(parsed) };
      }
    } catch {
      // Unreadable library.md -> no pin.
    }
  }

  return undefined;
}

export function label(p: PinnedProfile): string {
  const head = `CODESYS V3.5 SP${p.sp}`;
  return p.patch === 0 ? head : `${head} Patch ${p.patch}`;
}

/**
 * Compares the project's pinned version against the server's configured one.
 *
 * `saves` marks tools that write the .project back (bump/release). Those are
 * the ones that actually perform the conversion, so they refuse on any
 * mismatch and on an unknown-but-required pin. Read-only tools warn, because
 * a warning is enough to stop a human before they run the release, and
 * refusing every read would break existing unpinned repos.
 */
export function decideVersionPin(
  pin: VersionPin | undefined,
  server: PinnedProfile | undefined,
  opts: { saves: boolean; allowUpgrade?: boolean; projectFilePath: string }
): PinDecision {
  if (opts.allowUpgrade) return { action: 'proceed' };
  // Can't compare against an unparseable server profile -- stay out of the way.
  if (!server) return { action: 'proceed' };

  if (!pin) {
    if (!opts.saves) return { action: 'proceed' };
    return {
      action: 'refuse',
      message:
        `Refused: cannot confirm which CODESYS version this project was authored in, ` +
        `and this tool saves the .project.\n\n` +
        `A .project is not a ZIP, so the version cannot be read from the file -- it has to be ` +
        `pinned in the repo. Create a one-line ${PIN_FILE} next to the project:\n\n` +
        `  echo 3.5.${server.sp}.${server.patch * 10} > "${path.join(path.dirname(opts.projectFilePath), PIN_FILE)}"\n\n` +
        `...but ONLY if ${label(server)} really is what this project was authored in. If it is ` +
        `older, saving here converts it -- open it on the matching install instead. Re-run with ` +
        `allowVersionUpgrade: true to override deliberately.`,
    };
  }

  if (pin.sp === server.sp && pin.patch === server.patch) return { action: 'proceed' };

  const older = server.sp > pin.sp || (server.sp === pin.sp && server.patch > pin.patch);
  const direction = older ? 'UPGRADE' : 'DOWNGRADE';
  const detail =
    `Project is pinned to ${label(pin)} (via ${pin.source}: "${pin.raw}"), ` +
    `this server is ${label(server)}.`;

  if (!opts.saves) {
    return {
      action: 'proceed-with-warning',
      message:
        `⚠ CODESYS version mismatch -- ${detail} Opening is tolerated, but do NOT run a ` +
        `release from this server: saving would ${direction} the project.`,
    };
  }

  return {
    action: 'refuse',
    message:
      `Refused: saving would ${direction} the project. ${detail}\n\n` +
      `A newer CODESYS silently converts an older project on save, and the committed binary ` +
      `then stops being the software that is on the device.\n\n` +
      `Open it on the matching install instead:\n` +
      `  codesys-mcp-sp21-plus --print-config --for-project "${opts.projectFilePath}"\n\n` +
      `If the ${direction.toLowerCase()} is genuinely intended, re-run with allowVersionUpgrade: true.`,
  };
}
