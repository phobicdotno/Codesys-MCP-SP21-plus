import * as fs from 'fs';
import * as path from 'path';

export interface CodesysInstall {
  installDir: string;
  exePath: string;
  version: string;
  major: number;
  minor: number;
  sp: number;
  patch: number;
  profileName: string;
  serverName: string;
  /**
   * The AdditionalFolders installation carrying the most registered plugins,
   * if any. See LauncherConfig.additionalFolder -- without passing this the
   * IDE boots the bare base profile and scripting is unavailable.
   */
  additionalFolder?: string;
}

const VERSION_RE = /^CODESYS\s+(\d+)\.(\d+)\.(\d+)\.(\d+)$/i;

/**
 * Pick the richest AdditionalFolders installation for an install dir.
 *
 * The CODESYS Installer writes one folder per "Installation", each with its
 * own Profiles\<name>.profile.xml listing that installation's plugins. Every
 * one of them reuses the base profile NAME, so the name alone can't tell them
 * apart -- we rank by how many plugins each registers and take the fullest.
 * Returns undefined when there are no AdditionalFolders (the common case for
 * a stock install, where the base profile already has everything).
 */
function findRichestAdditionalFolder(
  installDir: string,
  fsApi: {
    readdirSync: typeof fs.readdirSync;
    readFileSync?: typeof fs.readFileSync;
  }
): string | undefined {
  const readFileSync = fsApi.readFileSync;
  if (!readFileSync) return undefined;

  const root = path.join(installDir, 'CODESYS', 'AdditionalFolders');
  let entries: string[];
  try {
    entries = fsApi.readdirSync(root);
  } catch {
    return undefined;
  }

  let best: { dir: string; plugins: number } | undefined;
  for (const entry of entries) {
    const dir = path.join(root, entry);
    const profilesDir = path.join(dir, 'Profiles');
    let profiles: string[];
    try {
      profiles = fsApi.readdirSync(profilesDir).filter((f) => f.toLowerCase().endsWith('.profile.xml'));
    } catch {
      continue;
    }

    let plugins = 0;
    for (const profile of profiles) {
      try {
        const xml = readFileSync(path.join(profilesDir, profile), 'utf-8');
        plugins += (xml.match(/<Hint>/g) ?? []).length;
      } catch {
        /* unreadable profile -- treat as contributing nothing */
      }
    }

    if (plugins > 0 && (!best || plugins > best.plugins)) {
      best = { dir, plugins };
    }
  }

  return best?.dir;
}

/**
 * Parse a CODESYS profile name like "CODESYS V3.5 SP22 Patch 1" or
 * "CODESYS V3.5 SP21" into its SP + patch numbers.
 *
 * Returns null when the name doesn't match the canonical CODESYS profile
 * shape -- callers should treat that as "can't decide" and skip whatever
 * behaviour the parsed values would have driven (e.g. open_project's
 * pre-flight mismatch check falls through silently).
 */
const PROFILE_NAME_RE = /^CODESYS\s+V\d+\.\d+\s+SP(\d+)(?:\s+Patch\s+(\d+))?\s*$/i;

export function parseProfileName(name: string): { sp: number; patch: number } | null {
  if (!name) return null;
  const m = PROFILE_NAME_RE.exec(name.trim());
  if (!m) return null;
  const sp = parseInt(m[1], 10);
  const patch = m[2] !== undefined ? parseInt(m[2], 10) : 0;
  if (Number.isNaN(sp) || Number.isNaN(patch)) return null;
  return { sp, patch };
}

function deriveProfileName(major: number, minor: number, sp: number, patch: number): string {
  const head = `CODESYS V${major}.${minor} SP${sp}`;
  return patch === 0 ? head : `${head} Patch ${patch}`;
}

function deriveServerName(sp: number, patch: number): string {
  const head = `codesys-sp${sp}`;
  return patch === 0 ? head : `${head}-patch${patch}`;
}

export function detectInstalls(
  searchDirs: string[] = ['C:\\Program Files', 'C:\\Program Files (x86)'],
  fsApi: {
    readdirSync: typeof fs.readdirSync;
    existsSync: typeof fs.existsSync;
    // Optional so existing injected fakes keep compiling -- without it we just
    // can't rank AdditionalFolders and leave additionalFolder undefined.
    readFileSync?: typeof fs.readFileSync;
  } = fs
): CodesysInstall[] {
  const installs: CodesysInstall[] = [];
  const seen = new Set<string>();

  for (const base of searchDirs) {
    let entries: string[];
    try {
      entries = fsApi.readdirSync(base);
    } catch {
      continue;
    }
    for (const entry of entries) {
      const m = VERSION_RE.exec(entry);
      if (!m) continue;
      const major = parseInt(m[1], 10);
      const minor = parseInt(m[2], 10);
      const sp = parseInt(m[3], 10);
      const rawPatch = parseInt(m[4], 10);
      const patch = Math.floor(rawPatch / 10);

      const exePath = path.join(base, entry, 'CODESYS', 'Common', 'CODESYS.exe');
      if (!fsApi.existsSync(exePath)) continue;
      if (seen.has(exePath.toLowerCase())) continue;
      seen.add(exePath.toLowerCase());

      installs.push({
        installDir: path.join(base, entry),
        exePath,
        version: `${major}.${minor}.${sp}.${rawPatch}`,
        major,
        minor,
        sp,
        patch,
        profileName: deriveProfileName(major, minor, sp, patch),
        serverName: deriveServerName(sp, patch),
        additionalFolder: findRichestAdditionalFolder(path.join(base, entry), fsApi),
      });
    }
  }

  installs.sort((a, b) => {
    if (a.sp !== b.sp) return a.sp - b.sp;
    return a.patch - b.patch;
  });

  return installs;
}

export interface PrintConfigOptions {
  sp?: number;
  name?: string;
  date?: string;
  /**
   * When set, the caller has already pre-filtered `installs` based on a
   * .project file's saved profile (see --for-project in bin.ts). printConfig
   * just renders -- the matching logic stays in bin.ts so detect.ts can stay
   * independent of inspect.ts. The hint drives the header comment block.
   */
  forProjectHint?: {
    profileName: string;
    profileVersion: string;
    matchKind: 'exact' | 'sp-only-fallback';
  };
}

export function printConfig(installs: CodesysInstall[], opts: PrintConfigOptions = {}): string {
  let filtered = installs;
  if (opts.sp !== undefined) {
    filtered = installs.filter((i) => i.sp === opts.sp);
  }

  if (filtered.length === 0) {
    if (opts.sp !== undefined) {
      throw new Error(
        `No CODESYS V3.5 SP${opts.sp} installation detected. Run \`codesys-mcp-sp21-plus --detect\` to see what's available.`
      );
    }
    throw new Error(
      `No CODESYS installations detected. Looked under "C:\\Program Files" and "C:\\Program Files (x86)" for "CODESYS X.Y.Z.W"-named directories with a CODESYS\\Common\\CODESYS.exe inside. Run \`codesys-mcp-sp21-plus --detect\` for raw output.`
    );
  }

  if (opts.name !== undefined && filtered.length !== 1) {
    throw new Error(
      `--name only works when exactly one install is selected. Got ${filtered.length}. Combine with --sp <n> to narrow down.`
    );
  }

  const today = opts.date ?? new Date().toISOString().slice(0, 10);
  const lines: string[] = [];

  lines.push(`// Auto-generated by \`codesys-mcp-sp21-plus --print-config\` on ${today}.`);
  if (filtered.length === 1) {
    lines.push(`// Detected 1 CODESYS installation.`);
  } else {
    lines.push(`// Detected ${filtered.length} CODESYS installations. Add the entries you want; remove the rest.`);
    lines.push(`//`);
    lines.push(`// Multiple entries can be active at the same time -- different CODESYS`);
    lines.push(`// installs (e.g. SP21 + SP22) spawn separate processes and run side by side.`);
    lines.push(`// The only hard rule: don't open the SAME .project file from two CODESYS`);
    lines.push(`// instances simultaneously -- file-lock contention pops a "project is`);
    lines.push(`// currently in use" modal that blocks all script execution.`);
  }
  if (opts.forProjectHint) {
    lines.push(`//`);
    if (opts.forProjectHint.matchKind === 'exact') {
      lines.push(
        `// Filtered by --for-project: matches ${opts.forProjectHint.profileName} (project saved on ${opts.forProjectHint.profileVersion})`
      );
    } else {
      lines.push(
        `// No exact match for project's saved profile (${opts.forProjectHint.profileName}, version ${opts.forProjectHint.profileVersion}).`
      );
      lines.push(
        `// Falling back to all installed SP${opts.forProjectHint.profileName.match(/SP(\d+)/)?.[1] ?? '?'} versions. The patch difference will trigger`
      );
      lines.push(
        `// a CODESYS conversion dialog on first open.`
      );
    }
  }
  lines.push(`//`);
  lines.push(`// Profile names are derived from the install directory version. If CODESYS's`);
  lines.push(`// own Profile dialog shows a different name (e.g. localised), edit the`);
  lines.push(`// --codesys-profile value to match exactly.`);
  lines.push('');

  const usedNames = new Set<string>();
  const namedEntries = filtered.map((install, idx) => {
    let name: string;
    if (opts.name !== undefined) {
      name = opts.name;
    } else if (filtered.length === 1) {
      name = 'codesys';
    } else {
      name = install.serverName;
    }
    let unique = name;
    let suffix = 2;
    while (usedNames.has(unique)) {
      unique = `${name}-${suffix++}`;
    }
    usedNames.add(unique);
    return { name: unique, install, isLast: idx === filtered.length - 1 };
  });

  lines.push('{');
  lines.push('  "mcpServers": {');
  for (const { name, install, isLast } of namedEntries) {
    lines.push(`    ${JSON.stringify(name)}: {`);
    lines.push(`      "command": "codesys-mcp-sp21-plus",`);
    lines.push(`      "args": [`);
    lines.push(`        "--codesys-path", ${JSON.stringify(install.exePath)},`);
    lines.push(`        "--codesys-profile", ${JSON.stringify(install.profileName)},`);
    if (install.additionalFolder) {
      lines.push(`        "--codesys-additional-folder", ${JSON.stringify(install.additionalFolder)},`);
    }
    lines.push(`        "--mode", "persistent"`);
    lines.push(`      ]`);
    lines.push(`    }${isLast ? '' : ','}`);
  }
  lines.push('  }');
  lines.push('}');

  return lines.join('\n');
}
