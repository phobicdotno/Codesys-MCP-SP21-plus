# Live source-control diff (`--auto-mirror`)

When `--auto-mirror` is added to the server args, every successful modifying tool call (`set_pou_code`, `create_pou`, `rename_object`, `add_library`, ...) is followed by an automatic `mirror_export`. The textual `<projectDir>/mcp-mirror/` tree is refreshed on disk in lock-step with the binary `.project`, so an external editor watching the folder sees the change immediately. The first refresh on a given project also fires `code --add <mirrorDir>` once, which appends the mirror folder to your active VSCode window so the diff shows up in the Source Control panel.

Since v0.17.0, the export also prunes mirror files whose objects were deleted or renamed, plus any directories left empty - only files carrying the CODESYS-export header comment are ever removed, and pruning is skipped when the export walk had errors.

> **Multiple projects in one folder:** when two or more `.project` files share a parent dir, each project gets its own mirror at `<projectDir>/<projectname>_mcp_mirror/` instead (e.g. `ProjectA.project` -> `ProjectA_mcp_mirror/`, `ProjectB.project` -> `ProjectB_mcp_mirror/`) so the exports don't clobber each other. Existing setups with a `mcp-mirror/` directory keep using it as-is, regardless of how many `.project` siblings are present, so v* tag history stays intact.

Enable it by adding the flag to the relevant entry's `args` in `.mcp.json`:

```jsonc
"args": [
  "--codesys-path", "...",
  "--codesys-profile", "...",
  "--mode", "persistent",
  "--auto-mirror"
]
```

Recommended one-time setup so the Source Control panel has a baseline to diff against:

```bash
cd <projectDir>/mcp-mirror
git init && git add -A && git commit -m "baseline"
```

After that, watch VSCode's Source Control panel as Claude edits - every tool call shows up as a real diff. The VSCode hook is best-effort: if the `code` CLI shim isn't on the standard path, the mirror still refreshes silently and the response carries an `(auto-mirror: refreshed)` hint instead of opening a window.
