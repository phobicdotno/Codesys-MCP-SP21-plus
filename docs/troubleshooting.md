# Execution Modes & Troubleshooting

## Persistent Mode (default, SP21+ rewrite)

1. Server launches `CODESYS.exe` with `--runscript=watcher.py` (no `--noUI`)
2. CODESYS UI opens - user can see and interact with the IDE
3. The watcher runs **single-threaded on the primary thread**, polling a `commands/` directory and yielding to the IDE via `system.delay()` between polls (this fork - upstream used a background thread + `system.execute_on_primary_thread()` which was removed in SP21)
4. When a tool is called, the server writes a `.py` script + `.command.json` to `commands/`
5. The watcher detects the command, executes it directly on the primary thread, and writes results atomically to `results/`
6. Changes made by tools appear in the CODESYS UI in real-time
7. The UI remains interactive between commands - only briefly paused during synchronous API calls (compile, open)

Internals (IPC protocol, atomicity, lifecycle) are documented in [../ARCHITECTURE.md](../ARCHITECTURE.md).

## Headless Mode

The original approach: each tool call spawns a new CODESYS process with `--noUI`, runs the script, and exits. No UI is shown. Used **only** when:

- `--mode headless` is specified, or
- Persistent mode fails to launch and `--fallback-headless` is explicitly opted in (off by default)

Persistent mode never silently degrades to headless. With `--no-auto-launch`, the first tool call lazy-launches the visible IDE; after `shutdown_codesys`, the next tool call relaunches it. Headless spawns are avoided because their modal dialogs are invisible (calls just abort), they hold `.project` locks, and they leave orphaned `CODESYS.exe` processes behind.

## Troubleshooting

**CODESYS not found**
Verify the path with `--detect`. The executable is typically at:
`C:\Program Files\CODESYS 3.5.XX.X\CODESYS\Common\CODESYS.exe`

**Project file locked**
Another CODESYS instance may have the project open. Close it first or use persistent mode so there's only one instance. The launcher will refuse to spawn a second `CODESYS.exe` of the same install.

**Watcher timeout (persistent mode)**
If the watcher doesn't signal ready within the timeout (150s to allow slow-plugin installs), check:
- CODESYS path and profile are correct
- No modal dialogs are blocking CODESYS startup
- Try `--verbose` for detailed logging

**"no script engine implementation available" / contradictory load dialog**
The install has multiple profiles sharing one name; pass `--codesys-additional-folder` - see [installs-and-profiles.md](installs-and-profiles.md).

**UI briefly pauses during commands (persistent mode)**
The watcher executes commands on the primary thread and yields between polls, so the UI stays responsive between commands. During synchronous CODESYS API calls (compile, project open), the UI may briefly pause - this is expected and normal. If a command hangs, check the CODESYS messages window for modal dialogs or errors.

**Command timeout**
Default is 60s (120s for compile and download). Increase with `--timeout <ms>`. Check the CODESYS messages window for errors.

**Online/runtime tools fail**
The online tools (`connect_to_device`, `read_variable`, etc.) require:
- A device/gateway configured in the CODESYS project
- The project to be compiled successfully before connecting
- A reachable PLC or CODESYS SoftPLC runtime

**"Refusing to switch projects: ... has UNSAVED changes"**
A tool addressed project B while project A was open with unsaved changes. Since v0.17.0 the server never saves A on its own - call `save_project` (to keep the changes) or `close_project` with `saveFirst=false` (to discard them), then retry.
