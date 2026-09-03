# Use with OpenAI Codex CLI

`codesys-mcp-sp21-plus` is a standard **stdio** MCP server, so any MCP-capable client can drive it - not just Claude Code. OpenAI's Codex CLI stores MCP servers in a TOML file rather than a JSON `.mcp.json`.

**Config file location:**

- Global: `~/.codex/config.toml` (Windows: `%USERPROFILE%\.codex\config.toml`)
- Per-project (trusted projects only): `.codex/config.toml` in the repo root

**Translate the `--print-config` output into a `[mcp_servers.<name>]` table.** `--print-config` emits Claude Code's JSON, but the `command` and `args` are identical - only the wrapper format differs. Run `codesys-mcp-sp21-plus --detect` first to get the exact path + profile string, then:

```toml
[mcp_servers.codesys-sp21]
command = "codesys-mcp-sp21-plus"
args = [
  "--codesys-path", "C:\\Program Files\\CODESYS 3.5.21.50\\CODESYS\\Common\\CODESYS.exe",
  "--codesys-profile", "CODESYS V3.5 SP21 Patch 5",
  "--mode", "persistent",
  "--no-auto-launch",
]
# CODESYS's first launch / a full compile can take 60s+. Codex defaults are
# startup_timeout_sec = 10 and tool_timeout_sec = 60 - raise the per-tool one.
tool_timeout_sec = 180

# Optional: pre-register PLC credentials so the "Device User Login" modal is
# suppressed on connect_to_device / download_to_device.
[mcp_servers.codesys-sp21.env]
CODESYS_DEVICE_USER = "<user>"
CODESYS_DEVICE_PASSWORD = "<password>"
```

For multiple CODESYS installs, add a second table (`[mcp_servers.codesys-sp22]`) with its own `--codesys-path` / `--codesys-profile` - the TOML equivalent of the multi-install `.mcp.json` block in [installs-and-profiles.md](installs-and-profiles.md).

Or let Codex write the entry for you instead of editing the file by hand:

```bash
codex mcp add codesys-sp21 \
  --env CODESYS_DEVICE_USER=<user> --env CODESYS_DEVICE_PASSWORD=<password> \
  -- codesys-mcp-sp21-plus \
     --codesys-path "C:\Program Files\CODESYS 3.5.21.50\CODESYS\Common\CODESYS.exe" \
     --codesys-profile "CODESYS V3.5 SP21 Patch 5" \
     --mode persistent --no-auto-launch
```

Notes:

- **Differences from Claude Code's config:** a TOML `[mcp_servers.<name>]` table (note the underscore) instead of the JSON `mcpServers` object; `env` is a TOML table (or inline `env = { KEY = "val" }`); there's no outer wrapper object.
- **`--no-auto-launch` is recommended here too** so CODESYS opens on the first tool call rather than when Codex spawns the server (otherwise the launch runs during startup and can exceed `startup_timeout_sec`).
- **Restart Codex after editing `config.toml`** - the MCP client only reads it at startup.
- Everything else is identical because it's the same binary: one `CODESYS.exe` at a time, exact `--codesys-profile` strings (copy from `--detect`), `--for-project`, `--auto-mirror`, etc.
