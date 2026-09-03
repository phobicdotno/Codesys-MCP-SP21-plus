# CLI Reference

| Flag | Description | Default |
|------|-------------|---------|
| `-p, --codesys-path <path>` | Path to CODESYS executable | `$CODESYS_PATH` or auto-detected |
| `-f, --codesys-profile <name>` | CODESYS profile name | `$CODESYS_PROFILE` or `CODESYS V3.5 SP21` |
| `--codesys-additional-folder <dir>` | Installer-managed AdditionalFolders dir that disambiguates same-named profiles (see [installs-and-profiles.md](installs-and-profiles.md)) | auto-detected by `--print-config` |
| `-w, --workspace <dir>` | Workspace directory for relative paths | Current directory |
| `-m, --mode <mode>` | `persistent` (UI) or `headless` (--noUI) | `persistent` |
| `--no-auto-launch` | Don't launch CODESYS on startup | Auto-launch enabled |
| `--fallback-headless` | Fall back to headless (`--noUI`) if persistent launch fails | `false` |
| `--keep-alive` | Keep CODESYS running after server stops | `false` |
| `--auto-mirror` | Refresh the textual mirror after every modifying tool call (see [auto-mirror.md](auto-mirror.md)) | off |
| `--timeout <ms>` | Default command timeout | `60000` |
| `--detect` | List installed CODESYS versions and exit | - |
| `--print-config` | Print a ready-to-paste `.mcp.json` snippet for every detected install and exit | - |
| `--sp <number>` | With `--print-config`: emit only the entry for CODESYS V3.5 SP`<n>` | - |
| `--for-project <path>` | With `--print-config`: pick only the install(s) matching the `.project` file at `<path>` (exact SP+patch, or fall back to same-SP-different-patch). Mutually exclusive with `--sp`. | - |
| `--name <name>` | With `--print-config --sp <n>`: override the MCP server entry name | - |
| `--inspect <path>` | Read a CODESYS `.project` offline (no CODESYS needed) and print its profile name/version + mandatory libraries; uses the `unzip` CLI from Git for Windows / Linux+Mac | - |
| `--ssh-version <host>` | SSH to a CODESYS Control Linux PLC and print the running project version (extracted from the boot-application binary). Bypasses CODESYS entirely. Requires SSH key auth + passwordless sudo for `strings`. | - |
| `--ssh-user <name>` | With `--ssh-version`: SSH user | `karstein` |
| `--ssh-boot-app <path>` | With `--ssh-version`: path to the boot application on the PLC | `/var/opt/codesys/PlcLogic/Application/Application.app` |
| `--verbose` | Enable verbose logging | - |
| `--debug` | Enable debug logging | - |
| `-V, --version` | Show version number | - |
| `-h, --help` | Show help | - |

Environment variables `CODESYS_PATH` and `CODESYS_PROFILE` are used as defaults when the corresponding flags are not provided. `CODESYS_DEVICE_USER` / `CODESYS_DEVICE_PASSWORD` pre-register PLC credentials so the "Device User Login" dialog is suppressed on `connect_to_device` / `download_to_device`.

## Run without `.mcp.json`

The binary can be invoked directly from a shell (useful for one-off testing or wrapping in another launcher):

```bash
codesys-mcp-sp21-plus \
  --codesys-path "C:\Program Files\CODESYS 3.5.22.10\CODESYS\Common\CODESYS.exe" \
  --codesys-profile "CODESYS V3.5 SP22 Patch 1"
```

## Detect installed versions

```bash
codesys-mcp-sp21-plus --detect
```

Scans `Program Files` and `Program Files (x86)` for CODESYS installations and prints each install's path and profile name.

## `--ssh-version` - read the running PLC's project version over SSH

For CODESYS Control Linux PLCs (Raspberry Pi, IPC, etc.) the running project version can be read straight off the boot-application binary, without CODESYS being installed or the `.project` file being unlocked:

```bash
codesys-mcp-sp21-plus --ssh-version 192.168.1.83
codesys-mcp-sp21-plus --ssh-version myplc.lan --ssh-user pi
```

Requires SSH key auth + passwordless sudo for `/usr/bin/strings` on the PLC. If your key isn't installed yet, the error message includes a one-line PowerShell recipe; full setup instructions live at [ssh-key-windows.md](https://gitlab.usv.no/karstein.kvistad/mr-ai-context/-/blob/main/ssh-key-windows.md).
