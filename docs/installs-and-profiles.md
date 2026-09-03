# CODESYS Installs, Profiles and Version Pinning

## Multiple CODESYS installations

The MCP server is bound to a **single** `--codesys-path` / `--codesys-profile` at startup. `launch_codesys` takes no parameters - it just starts whichever CODESYS the server was configured against. If you have several CODESYS versions installed and want to drive them all from the same Claude Code session, register **one MCP server entry per install** with a distinct name.

Both blocks below live in the same `.mcp.json`. Claude can call either by name (`codesys-21` / `codesys-22`) and the two run as independent processes with independent CODESYS instances:

```json
{
  "mcpServers": {
    "codesys-21": {
      "command": "codesys-mcp-sp21-plus",
      "args": [
        "--codesys-path", "C:\\Program Files\\CODESYS 3.5.21.50\\CODESYS\\Common\\CODESYS.exe",
        "--codesys-profile", "CODESYS V3.5 SP21 Patch 5",
        "--mode", "persistent"
      ]
    },
    "codesys-22": {
      "command": "codesys-mcp-sp21-plus",
      "args": [
        "--codesys-path", "C:\\Program Files\\CODESYS 3.5.22.10\\CODESYS\\Common\\CODESYS.exe",
        "--codesys-profile", "CODESYS V3.5 SP22 Patch 1",
        "--mode", "persistent"
      ]
    }
  }
}
```

Notes:

- The version numbers (`3.5.21.50`, `3.5.22.10`) match the install directory names under `C:\Program Files\` - these are the actual install IDs CODESYS uses, not the marketing names. The marketing name lives in `--codesys-profile` (e.g., `CODESYS V3.5 SP21 Patch 5`, `CODESYS V3.5 SP22 Patch 1`).
- Run `codesys-mcp-sp21-plus --detect` once to print every CODESYS install the server can see, with its profile name; copy the values from there into `.mcp.json` rather than guessing.
- Each server entry spawns its own CODESYS process when first invoked. Don't call `launch_codesys` on both at the same time pointing at projects that overlap - two CODESYS instances racing on the same `.project` file pop a "project is currently in use" modal that blocks every subsequent script.
- Adding or removing an entry requires a Claude Code restart (the MCP client only reads `.mcp.json` at startup).

If you have a specific `.project` file in mind and don't want to eyeball which install opens it, point `--for-project` at the file and `--print-config` will narrow the snippet to just the matching install (or warn and fall back to same-SP-different-patch if no exact match exists). The match is driven by the project's saved `projectinspectiondata.auxiliary` profile, so it works without launching CODESYS:

```bash
codesys-mcp-sp21-plus --print-config --for-project "C:\path\to\MyMachine.project"
```

> **Caveat:** `--for-project` reads `projectinspectiondata.auxiliary` out of the project ZIP.
> That entry exists in `.projectarchive` files, but a plain **`.project` is not a ZIP** - it is a
> compressed CODESYS container (magic `23 89 ED 33`) with no readable profile string. On a plain
> `.project`, `--for-project` finds nothing and falls back to the default install. Use the version
> pin below to protect real projects.

## `--codesys-additional-folder`: where the add-on packages actually live

If launching produces *"The command line option 'runscript' has been set. However, there is no
script engine implementation available"*, or a load dialog that appears to contradict itself -

> The project file has been created with CODESYS V3.5 SP19 Patch 2 and contains data that cannot
> be loaded by CODESYS V3.5 SP19 Patch 2.

- the install has **multiple profiles sharing one name**.

The CODESYS Installer registers add-on packages (Script Engine, device support, ...) into a
per-installation directory:

```
<install>\CODESYS\AdditionalFolders\<InstallationName>\Profiles\<ProfileName>.profile.xml
```

Every one of those carries the *same* `<ProfileName>` as the bare base profile in
`<install>\CODESYS\Profiles\`, but a different set of registered plugins. So `--profile` alone is
ambiguous: CODESYS resolves it to the base profile, which on an installer-managed box can have
**zero** plugins. That's both symptoms above - no Script Engine, and "missing packages" phrased in
terms of a profile name that matches.

The shortcut the installer drops in the Start Menu passes the disambiguator; so must this server:

```jsonc
"--codesys-profile", "CODESYS V3.5 SP19 Patch 2",
"--codesys-additional-folder", "C:\\Program Files\\CODESYS 3.5.19.20\\CODESYS\\AdditionalFolders\\MyInstallation",
```

`--detect` / `--print-config` find this for you: they rank every `AdditionalFolders\*` by how many
plugins its profile registers and emit the fullest one. Installs with no `AdditionalFolders` (the stock
case - everything is in the base profile) get no flag, which is correct.

To check by hand, compare plugin counts across the same-named profiles:

```powershell
Get-ChildItem "C:\Program Files\CODESYS 3.5.19.20\CODESYS" -Recurse -Filter "*.profile.xml" |
  ForEach-Object { "{0,-4} {1}" -f (Select-String $_ -Pattern '<Hint>' -AllMatches).Matches.Count, $_.FullName }
```

## Version pin: never silently convert a project

Opening a project in a CODESYS **newer** than the one that authored it converts it on save. The
`.project` on disk is then no longer the software running on the device - and if that save happened
inside `release_project_version`, the wrong binary is already committed, tagged and pushed.

Because the authored version can't be read out of a `.project` (see the caveat above), it is pinned
in the repo instead. Two sources, most specific first:

1. **`.codesys-version`** next to the `.project` - one line, either `3.5.19.20` or
   `CODESYS V3.5 SP19`. `#` comments and blank lines are skipped. This is the only option when
   seeding a project that has no release history yet.
2. **`library.md`** - the `CODESYS Development System` row of a previously generated inventory.
   Every project gets a pin for free after its first release.

```bash
echo 3.5.19.20 > "C:\plc\MyVessel\.codesys-version"
```

The guard is deliberately asymmetric, so it protects the dangerous path without getting in the way:

| Tool | Pin matches | Pin differs | No pin |
|---|---|---|---|
| `bump_project_version`, `release_project_version` (**save** the project) | proceed | **refuse** | **refuse** |
| `get_project_info`, `mirror_export`, `list_project_libraries` (read only) | proceed | warn | proceed |

Both saving tools take `allowVersionUpgrade: true` to override when the conversion is deliberate.
Read-only tools never refuse - a warning is enough to stop a human before they run the release, and
refusing every read would break existing unpinned repos.

Note this is a *different* mechanism from the `open_project` pre-flight in `src/preflight.ts`, which
compares the ZIP-derived profile and therefore no-ops on plain `.project` files.
