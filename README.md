# Codesys-MCP-SP21+

> **This is a fork.** It is **not** the upstream `luke-harriman/Codesys-MCP`.
>
> - **Upstream:** [luke-harriman/Codesys-MCP](https://github.com/luke-harriman/Codesys-MCP)
> - **npm:** [`codesys-mcp-sp21-plus`](https://www.npmjs.com/package/codesys-mcp-sp21-plus) (published by `phobic`)
> - **Maintainer:** Karstein Kvistad
>
> **Why fork.** Upstream's watcher relies on `system.execute_on_primary_thread()` to marshal work from a background thread back to the CODESYS UI thread. That API was **removed in CODESYS V3.5 SP21+**, so on SP21 / SP22 every tool call returned the same `Marshal error: The functionality 'system.execute_on_primary_thread(...)' is no longer supported` and the server was effectively unusable on current CODESYS releases. Several other upstream tools were also broken by unrelated script-engine API drift. This fork fixes all of that and adds a release pipeline on top.

MCP server for CODESYS with a persistent UI instance and file-based IPC. Unlike headless-only approaches that spawn a new CODESYS process per command, this server launches CODESYS **with its UI visible** and keeps it running. MCP tool calls are sent to the same instance via a file-based IPC watcher, so changes appear in real-time and the user can interact with the IDE alongside AI-driven automation.

**106 MCP tools**: project/POU authoring, compile, online/runtime ops, device + task configuration, symbol configuration, NVL, multi-device projects, and a version-anchor + git release pipeline. Full catalogue in [docs/tools.md](docs/tools.md).

---

## Quick Start

**1. Install globally from npm:**

```bash
npm install -g codesys-mcp-sp21-plus
```

**2. Generate your `.mcp.json` snippet** - `--print-config` scans your installed CODESYS versions and emits a ready-to-paste block per install:

```bash
codesys-mcp-sp21-plus --print-config           # one entry per detected install
codesys-mcp-sp21-plus --print-config --sp 21   # only the SP21 entry, named "codesys"
```

Output looks like this on a machine with two installs:

```jsonc
{
  "mcpServers": {
    "codesys-sp21-patch5": {
      "command": "codesys-mcp-sp21-plus",
      "args": [
        "--codesys-path", "C:\\Program Files\\CODESYS 3.5.21.50\\CODESYS\\Common\\CODESYS.exe",
        "--codesys-profile", "CODESYS V3.5 SP21 Patch 5",
        "--mode", "persistent"
      ]
    },
    "codesys-sp22-patch1": { ... }
  }
}
```

**3. Paste into your MCP config:**

- **Project-scoped** (recommended, shareable via git): `<your-project-root>/.mcp.json`. Create it if it doesn't exist; merge the `mcpServers` entries into the existing object if it does.
- **User-scoped** (applies to every Claude Code session): `%USERPROFILE%/.claude.json`, or use `claude mcp add codesys codesys-mcp-sp21-plus -- --codesys-path ... --codesys-profile ...`.
- **Using OpenAI Codex instead of Claude Code?** It's the same stdio server - see [docs/codex-cli.md](docs/codex-cli.md) for the `config.toml` equivalent.

**4. Restart Claude Code** so it re-reads the MCP config.

Multiple CODESYS installs can be registered side by side (one entry per install) - see [docs/installs-and-profiles.md](docs/installs-and-profiles.md). The only hard rule: don't open the SAME `.project` from two CODESYS instances simultaneously.

## What this fork adds

Highlights - the full list with rationale is in [docs/whats-new.md](docs/whats-new.md):

- **SP21+/SP22 compatibility**: single-threaded watcher on the primary thread (upstream's marshaling API was removed in SP21). Works on SP19, SP21, SP22+.
- **Upstream tool fixes**: `set_pou_code` no longer wipes the omitted half of a POU, `create_folder`/`connect_to_device`/`compile_project` API drift fixed, `add_library` refuses to save unresolvable placeholders, project switching never silently saves the prior project.
- **SP21 full API coverage**: online/runtime ops (force, bulk read/write, boot app, source up/download, PLC files), project lifecycle and interop, device + task configuration (including array device parameters), symbol configuration, project users, NVL, multi-device projects with `applicationPath` on 50 tools.
- **Version anchor + release pipeline**: `bump_project_version` / `release_project_version` maintain a `_MCP_PROJECT_VERSION` GVL, classify changes via mirror diff, regenerate docs, and commit + tag + push in one call; `read_running_version_online` / `_ssh` read the version back off the live PLC.
- **Source mirror**: `mirror_export` renders the project as diffable `.st` files (with stale-file pruning); `--auto-mirror` refreshes it after every modifying call for a live VSCode diff - see [docs/auto-mirror.md](docs/auto-mirror.md).
- **Safety guards**: same-install second-instance refusal, SP-mismatch pre-flight on `open_project`, repo version pin so a newer CODESYS never silently converts a project.

## Installation

This is a Node.js MCP server published to npm as **`codesys-mcp-sp21-plus`**. It is **this fork** - not the upstream `luke-harriman/Codesys-MCP` and not a Python package. There is no `pip install`; the `.py` files under `src/scripts/` are CODESYS IronPython templates bundled inside the npm package itself.

**Requirements:** Node.js 18+, Windows, CODESYS 3.5 SP19, SP21 (3.5.21.x), or SP22 (3.5.22.x) installed.

### Install from npm (recommended)

```bash
npm install -g codesys-mcp-sp21-plus
```

Verify, then wire into `.mcp.json` per [Quick Start](#quick-start):

```bash
codesys-mcp-sp21-plus --version
codesys-mcp-sp21-plus --detect       # lists installed CODESYS versions
```

Upgrade later with `npm install -g codesys-mcp-sp21-plus@latest`.

### Install from source (development / unreleased changes)

```bash
git clone https://github.com/phobicdotno/Codesys-MCP-SP21-plus.git
cd Codesys-MCP-SP21-plus
npm install
npm run build
npm link
```

`npm link` registers `dist/bin.js` as the global `codesys-mcp-sp21-plus` binary, so the same `.mcp.json` snippet works. Edits to `src/` take effect after `npm run build`; Python script edits hot-reload from `dist/scripts/` without a rebuild. To update later: `git pull && npm install && npm run build`.

To avoid touching the global node_modules, skip `npm link` and point `.mcp.json` at the checkout directly: `"command": "node", "args": ["C:\\Users\\<you>\\Codesys-MCP-SP21-plus\\dist\\bin.js", "--codesys-path", ...]`.

## Documentation

| Doc | Contents |
|---|---|
| [docs/tools.md](docs/tools.md) | All 106 MCP tools + resources, per category, with fix/NEW annotations |
| [docs/cli-reference.md](docs/cli-reference.md) | Every CLI flag, env vars, `--detect`, `--ssh-version`, running without `.mcp.json` |
| [docs/installs-and-profiles.md](docs/installs-and-profiles.md) | Multiple CODESYS installs, `--for-project`, `--codesys-additional-folder`, the repo version pin |
| [docs/auto-mirror.md](docs/auto-mirror.md) | Live source-control diff via `--auto-mirror` |
| [docs/codex-cli.md](docs/codex-cli.md) | Using the server from OpenAI Codex CLI (TOML config) |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Execution modes (persistent vs headless) + troubleshooting table |
| [docs/whats-new.md](docs/whats-new.md) | Full fork changelog with rationale |
| [ARCHITECTURE.md](ARCHITECTURE.md) | IPC protocol, watcher internals, lifecycle, concurrency |
| [docs/migration-sp21-plus.md](docs/migration-sp21-plus.md) | Why upstream broke on SP21 and how the rewrite works |
| [docs/RELEASING.md](docs/RELEASING.md) | npm release procedure for this package |

## Development

```bash
npm install        # dependencies
npm run build      # compile TypeScript + copy Python scripts to dist/
npm test           # run all tests (vitest)
npm run typecheck  # tsc --noEmit
```

```
src/
  bin.ts              CLI entry point
  server.ts           MCP tool/resource registration (106 tools, 3 resources)
  launcher.ts         CODESYS process management
  ipc.ts              File-based IPC transport
  headless.ts         Headless fallback executor
  script-manager.ts   Python template loading + interpolation
  scripts/            IronPython scripts (watcher + helpers + tool scripts)
tests/
  unit/               Unit tests (IPC, script manager, launcher)
  integration/        Script-preparation tests (no CODESYS required)
```

## Credits

- Upstream project: [luke-harriman/Codesys-MCP](https://github.com/luke-harriman/Codesys-MCP) - original architecture, the persistent-watcher concept, and the bulk of the upstream tool set
- This fork: [phobicdotno/Codesys-MCP-SP21-plus](https://github.com/phobicdotno/Codesys-MCP-SP21-plus) - Karstein Kvistad. SP21+/SP22 watcher rewrite, upstream-tool fixes, version-anchor + release pipeline, source-mirror export

## License

MIT
