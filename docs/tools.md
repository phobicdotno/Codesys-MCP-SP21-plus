# MCP Tools & Resources

106 tools across the categories below. Tools marked **NEW** were added in this fork; tools marked **FIXED** existed upstream but were broken before this fork.

## Management Tools

| Tool | Description |
|------|-------------|
| `launch_codesys` | Manually launch CODESYS (use with `--no-auto-launch`) |
| `launch_codesys_with_project` | **NEW** - Launch a (potentially different) CODESYS install and open a project in it, detached from this MCP (no IPC, no watcher). For cross-version inspection or handing the user an IDE on another install |
| `shutdown_codesys` | Shut down the persistent CODESYS instance (kills orphans too) |
| `get_codesys_status` | Get current state, PID, execution mode |
| `get_user_selection` | **NEW** - The POU the user is currently looking at in the phobiCS-tui browser (freshness-checked snapshot). Grounds modifying calls in what the user has selected |

## Project Tools

| Tool | Description |
|------|-------------|
| `open_project` | Open an existing CODESYS project file (cross-project switch **FIXED**; SP-mismatch pre-flight **NEW**; refuses to switch away from a project with unsaved changes instead of silently saving it, v0.17.0) |
| `create_project` | Create a new project from the standard template |
| `save_project` | Save the currently open project |
| `compile_project` | Build the primary application with structured error output (120s timeout) - JSON `long` **FIXED** |
| `get_compile_messages` | Retrieve last compiler messages without triggering a new build - JSON `long` **FIXED** |

`open_project` runs an offline pre-flight (`projectinspectiondata.auxiliary` ZIP+XML - no CODESYS) that compares the project's saved profile against this server's `--codesys-profile`. Exact match proceeds silently; same-SP-different-patch proceeds with a one-line warning (CODESYS will pop its patch-difference dialog); SP mismatch refuses without opening so the project isn't dragged through a downgrade/upgrade conversion. The refusal includes a routing hint: pick a different MCP server entry or generate one with `codesys-mcp-sp21-plus --print-config --for-project "<projectFilePath>"`. If the inspection itself fails (file missing, malformed .project, non-standard profile name), pre-flight falls through silently and the existing CODESYS open path produces its native error.

## POU / Code Authoring Tools

| Tool | Description |
|------|-------------|
| `create_pou` | Create a Program, Function Block, or Function |
| `set_pou_code` | Set declaration and/or implementation code (omitted-field wipe **FIXED**) |
| `create_property` | Create a property within a Function Block |
| `create_method` | Create a method within a Function Block |
| `create_dut` | Create a Data Unit Type (Structure, Enumeration, Union, Alias) |
| `create_gvl` | Create a Global Variable List with optional initial declaration |
| `create_folder` | Create an organizational folder in the project tree (**FIXED**) |
| `delete_object` | Delete any project object (POU, DUT, GVL, folder, etc.) |
| `rename_object` | Rename any project object |
| `move_object` | Move an object to a new parent in the tree |
| `get_all_pou_code` | Bulk read all declaration and implementation code in the project (120s timeout) |

## Online / Runtime Tools

| Tool | Description |
|------|-------------|
| `connect_to_device` | Login to the PLC runtime - `LoginMode` signature + auto-login **FIXED**; **NEW** `deviceUser`/`devicePassword` args (or `CODESYS_DEVICE_USER`/`CODESYS_DEVICE_PASSWORD` env) pre-register credentials via `ScriptOnline.set_default_credentials` so the modal "Device User Login" dialog is suppressed |
| `disconnect_from_device` | Logout from the PLC runtime |
| `get_application_state` | Check if the PLC application is running, stopped, or in exception |
| `read_variable` | Read a live variable value from the running PLC (e.g., `PLC_PRG.bMotorRunning`) |
| `write_variable` | Write/force a variable value on the running PLC |
| `download_to_device` | Download compiled application to PLC (attempts online change first, 120s timeout); same `deviceUser`/`devicePassword` credential-injection support as `connect_to_device`. Runs `verify_device_reachable` as a pre-flight |
| `start_stop_application` | Start or stop the PLC application |
| `reset_application` | **NEW** - Reset the online application: `warm` (keep retains), `cold` (clear retains), `origin` (erase application from device - destructive) |
| `read_variables` | **NEW** - Bulk read: current values of many expressions in one call (`read_values`) |
| `write_variables` | **NEW** - Bulk write: stage many expression/value pairs, commit in one `write_prepared_values` batch (same-cycle landing) |
| `force_variables` | **NEW** - Force expression/value pairs (pinned against task writes until unforced) |
| `unforce_variables` | **NEW** - Unforce specific expressions (optionally restoring pre-force values) or ALL forced values |
| `list_forced_variables` | **NEW** - List all forced + prepared expressions on the online application |
| `create_boot_application` | **NEW** - Create a boot application on the connected device, or write an offline `.app` file |
| `source_download` | **NEW** - Store the project source archive on the PLC (compact or full) |
| `source_upload` | **NEW** - Retrieve the source archive stored on the PLC into a local `.prj` |
| `plc_file_list` | **NEW** - List a directory on the PLC filesystem (kind/name/size/mtime) |
| `plc_file_transfer` | **NEW** - Copy a single file to (`to_plc`) or from (`from_plc`) the PLC filesystem |
| `plc_file_delete` | **NEW** - Delete a file or directory on the PLC filesystem (destructive) |

## Project Lifecycle & Interop (**NEW**, SP21-coverage phase 2)

| Tool | Description |
|------|-------------|
| `close_project` | Close the open project (optionally saving first) |
| `save_project_as` | Save under a new path; set/disable encryption password |
| `save_project_archive` | Save a `.projectarchive` with default categories |
| `save_as_compiled_library` | Save the primary project as a `.compiled_library` |
| `export_plcopen_xml` / `import_plcopen_xml` | PLCopenXML interchange (whole project or subtree) |
| `export_native` / `import_native` | Lossless CODESYS native export/import |
| `get_project_info` / `set_project_info` | Project Information fields + custom properties |
| `get_compiler_version` / `set_compiler_version_to_newest` | Project compiler version |
| `clean_all` | Clean All (remove compile info) |

## Application Build & Object Ops (**NEW**, phase 3)

| Tool | Description |
|------|-------------|
| `application_build` | generate_code / rebuild / clean on the active application |
| `check_online_change` | Is an online change currently possible? |
| `get_signature_crc` | Signature CRC of a POU (API-compatibility checks) |
| `set_exclude_from_build` | Set/clear 'Exclude from build' on an object |

## Network Variable Lists (**NEW**, v0.16.0)

| Tool | Description |
|------|-------------|
| `set_nvl_sender` | Make a GVL an NVL sender (UDP): list identifier, task, interval, broadcast address, port, pack/checksum/acknowledge |
| `create_nvl_receiver` | Add a Network Variable List (Receiver) object bound to a sender GVL |

The scripting API has no NVL support; these tools use the IDE's Automation Platform API (`IGVLObject2.CreateNetVarProperties`, `INetVarProperties`, `INVLObject`) from the IronPython scripts, proven live on a two-device project (SystemInstances.ObjectMgr, reflective attach of detached NetVarProperties, receiver creation via ObjectFactoryManager).

## Multi-device projects (**NEW**, v0.16.0)

| Tool | Description |
|------|-------------|
| `list_applications` | Every application in the project with hosting device, full path and ACTIVE flag |
| `set_active_application` | Make one application the active one (`project.active_application`) and save |

All application-scoped tools also accept `applicationPath` (e.g. `'Master/Plc Logic/Application'`, `'Master'`, or a unique application name) and activate it before acting. Omit it in single-device projects. Path-based tools (`set_pou_code`, `create_method`, `move_object`, ...) resolve a relative `Application/...` path against the active application; use the full `Device/Plc Logic/Application/...` path to address the other device without switching.

## Device Config & Task Config (**NEW**, phase 4)

| Tool | Description |
|------|-------------|
| `list_device_parameters` / `get_device_parameter` / `set_device_parameter` | Walk and edit device + connector parameters (including WAGO K-Bus host parameters). Array/struct parameters: `set_device_parameter` writes whole arrays via a `'[v0, v1, ...]'` value or one element via `elementIndex`; `get_device_parameter` lists sub-elements (v0.17.0) |
| `export_io_mappings_csv` / `import_io_mappings_csv` | Bulk IO-mapping editing via CSV |
| `set_device_state` | enable / disable / simulation_on / simulation_off |
| `get_device_identification` | Device type/id/version, name, address, state |
| `add_device` | **NEW** - Add a child device under a parent in the tree (e.g. 'Modbus TCP Server' under an Ethernet adapter). Idempotent; refuses if the device repository has no matching descriptor |
| `update_device_type` | **NEW** - Change the PLC device type in-place, preserving the Application subtree (e.g. WAGO PFC200 to CODESYS Control for Raspberry Pi). Fails loud rather than falling back to remove+add |
| `list_tasks` | **NEW** - Tasks in the Task Configuration with best-effort properties and ordered POU call lists. Read-only |
| `create_task` / `configure_task` | Create tasks and set kind/priority/interval/event |
| `add_pou_to_task` | **NEW** - Append or insert a Program POU into a task's call list (blocked while logged into a device) |
| `remove_pou_from_task` | **NEW** - Remove a Program's call from a task (the POU object itself stays). Verifies the removal on a freshly re-walked task object after save (v0.17.0) |

## Project Users & Misc Objects (**NEW**, phase 5)

| Tool | Description |
|------|-------------|
| `list_project_users` / `add_project_user` / `remove_project_user` | Project access-protection user management |
| `create_text_list` / `import_text_list_file` | Text lists for visu texts/translations |
| `create_image_pool` | Image pools for visualizations |
| `add_external_file` | Embed/link an external file into the project |
| `restart_runtime_ssh` | **NEW** - SSH into a Linux PLC and restart `codesyscontrol` via password-fed `sudo -S`. After issuing `systemctl restart`, polls `ss -tln` for the runtime port (default 11740) until it actually comes up - works around `systemctl is-active` reporting "active" after the binary has died from license-demo expiry |

## Device Network / Access Management (**NEW**)

The gateway's cached device address goes stale every time the PLC reboots or gets a new router entry; these tools scan and re-bind without hand-editing the project. The two access-control tools cover the OPC UA prerequisites: the runtime user database (consulted for `UserIdentityToken`) and the project-side Access Control matrix on the Symbol Configuration object.

| Tool | Description |
|------|-------------|
| `scan_network_devices` | **NEW** - Drive the gateway's *Scan Network* on the project's configured device. Returns the live target list (`device_name`, `type_name`, `vendor_name`, `address`, `device_id`). `useCache=true` returns the gateway's last result without rescanning |
| `verify_device_reachable` | **NEW** - Pre-flight for `download_to_device` / `connect_to_device`: scans and reports whether the project's cached address still matches a live target. `download_to_device` runs this automatically |
| `rebind_device_to_scan_result` | **NEW** - Re-bind the project's configured device to a fresh scan result (same PLC, new address after reboot/DHCP). Match priority: `matchName` (exact, case-insensitive), then `matchDeviceId`, then `matchAddress` (forced, no scan), then single candidate. Refuses on ambiguity and returns the candidate list |
| `add_device_user` | **NEW** - Add (or update the password of) a user in the PLC runtime's live User Management. Required for OPC UA authentication on CODESYS Control SP16+ - without at least one user, UaExpert returns `BadIdentityTokenInvalid`. The OPC UA server reads its `UserIdentityToken` policies from this database, NOT from `CODESYSControl.cfg` |
| `grant_object_access` | **NEW** - Set Access Control permissions on a project object for a user group (mirrors *Properties, Access Control* in the IDE). Required before a downloaded OPC UA server exposes any token policies: if the group has no View/Modify on the Symbol Configuration, there's nothing to expose |

## Library Management Tools

| Tool | Description |
|------|-------------|
| `list_project_libraries` | List all libraries referenced in the project with version info, plus IDE version, devices, and per-Application compiler version (**FIXED** - switched to `ScriptLibManObjectContainer`) |
| `add_library` | Add a library reference. Pre-resolves via `library_manager.find_library` and prefers the managed-library overload; refuses to save if the resulting reference is an unresolvable placeholder (**hardened**) |
| `remove_library` | **NEW** - Remove a library reference from Library Manager. Idempotent: no-op + success if the named library isn't present. Accepts a bare name (`'Standard'`) or the fully-qualified `'Name, Version (Company)'` form to target a specific version when duplicates exist. Verifies removal in `lm.references` before saving |

## Symbol Configuration Tools (**NEW**)

Wraps `ScriptSymbolConfigObject` (CODESYS 3.5.10.0+). The Symbol Configuration object controls which IEC variables / FBs / methods are exposed to OPC UA, web visualisations, and other external clients. Reference: helpme-codesys.com/en/ScriptingEngine/ScriptSymbolConfigObject.html and the SP22 stub `Stubs/scriptengine/ScriptSymbolConfigObject.pyi`.

| Tool | Description |
|------|-------------|
| `find_symbol_config` | **NEW** - Locate the Symbol Configuration object(s) in the project tree (one per Application typically). Read-only |
| `list_all_signatures` | **NEW** - Every POU / FunctionBlock / Method / Function the symbol config could potentially export. `compile=true` forces an `application.build()` first |
| `list_all_datatypes` | **NEW** - Every DUT / struct / enum / alias / union (same `compile` semantics) |
| `list_configured_symbols` | **NEW** - Only those signatures + datatypes actually configured for export, with each variable's `configured_access` / `maximal_access` / `effective_access` |
| `get_symbol_config_settings` | **NEW** - Read every knob: `content_feature_flags` (OPC UA / IncludeComments / IncludeAttributes / IncludeExecutables / etc.), attribute filter, comment filter, direct I/O access (+ obstacles), client-side layout calculator |
| `create_symbol_config` | **NEW** - `application.create_symbol_config(...)` under a chosen Application. Idempotent: no-ops with success if a symbol config already exists anywhere in the tree |
| `set_symbol_config_settings` | **NEW** - Partial-update of any subset of the 6 knobs. Refuses to enable direct I/O if `check_effective_direct_io_access()` reports obstacles |
| `set_symbol_access` | **NEW** - Per-variable `configured_access` setter (`None` / `ReadOnly` / `WriteOnly` / `ReadWrite`). Locates the signature by FQN; works on not-yet-configured variables too |
| `set_signature_access_bulk` | **NEW** - Set every variable in one signature to the same access in one call |
| `export_symbol_xsd` | **NEW** - Write the schema bytes from `get_symbol_configuration_xsd()` to a file (UTF-8). Useful for downstream XML validation in CI |

## Version Anchor + Release Pipeline (**NEW**)

These tools maintain a `_MCP_PROJECT_VERSION` GVL inside the project so the running PLC carries its source version at a known address, and orchestrate the end-to-end release flow (mirror, classify, bump, regen .md, git commit + tag + push).

| Tool | Description |
|------|-------------|
| `bump_project_version` | **NEW** - Bump one part of the 4-part `Project Information.Version` (major / minor / revision / build / auto) and maintain `_MCP_PROJECT_VERSION.sVersion` in every application. `auto` mode classifies via mirror diff vs latest `v*` git tag |
| `release_project_version` | **NEW** - One-shot release pipeline: `mirror_export`, classify, `bump_project_version`, regenerate .md docs, `git add`, `git commit`, `git tag v<new>`, `git push --follow-tags`. Dual-SHA tag annotation. Preserves hand-maintained library.md sections across regeneration |
| `read_running_version_online` | **NEW** - Reads `_MCP_PROJECT_VERSION.sVersion` from the running PLC over the CODESYS online protocol (port 11740 / gateway). *Caveat: requires some IEC code to reference the variable so the optimizer doesn't strip it from the online symbol table - see the tool's error message for the one-line fix.* |
| `read_running_version_ssh` | **NEW** - SSH equivalent of `read_running_version_online`: extracts the `X.Y.Z.W` literal straight off the boot-application binary on a CODESYS Control Linux PLC. Bypasses CODESYS entirely - no IDE, no project lock, no online protocol. Requires SSH key auth + passwordless sudo for `strings`. Same engine as the `--ssh-version` CLI flag |

## Source Mirror (**NEW**)

| Tool | Description |
|------|-------------|
| `mirror_export` | **NEW** - Walks the project tree and writes one `.st` file per code-bearing object into `<projectDir>/mcp-mirror/`, preserving the project tree as nested directories. Prunes stale files of deleted/renamed objects and empty directories (only signature-matched export files, skipped when the walk had errors; v0.17.0). Read-only on the project. Foundation for the release pipeline classifier |

## MCP Resources

| Resource URI | Description |
|--------------|-------------|
| `codesys://project/status` | CODESYS scripting status and open project info |
| `codesys://project/{path}/structure` | Project tree structure |
| `codesys://project/{path}/pou/{pou}/code` | POU declaration and implementation code |
