import sys, scriptengine as script_engine, os, traceback

# Close + reopen the primary project to dispose accumulated editor views.
#
# Why: every scripted textual_declaration/textual_implementation write (and
# object creation) opens an editor view in the visible IDE, and the CODESYS
# ScriptEngine has NO API to close views -- ScriptCommands is lookup-only
# (name/description/tokens/guid, no execute; see ScriptSystem.pyi stubs and
# helpme-codesys ScriptingEngine/ScriptSystem.html), and editors are not
# reachable via UIA either (custom WinForms menus). After ~40-60 scripted
# edits the IDE pops "The user interface is running low on system resources"
# and every subsequent script call times out.
#
# Closing the project disposes all of its editor views; reopening restores
# the invariant that the primary project stays open for the next tool call.

try:
    primary_project = script_engine.projects.primary
    if primary_project is None:
        print("DEBUG: flush_editor_views: no primary project open; nothing to flush.")
        print("SCRIPT_SUCCESS: No project open, nothing flushed.")
        sys.exit(0)

    project_path = primary_project.path
    dirty = False
    try:
        dirty = bool(primary_project.dirty)
    except Exception:
        pass
    if dirty:
        primary_project.save()
        print("DEBUG: flush_editor_views: unsaved changes saved before close.")

    # Close is REFUSED while logged into a device, which silently defeated the
    # flush for whole online sessions (views piled up until the IDE died with
    # "running low on system resources" -- observed Sea Leopard 2026-07-24).
    # Log off first; the next online tool re-logs-in via ensure_online_connection
    # (credentials are pre-registered, so no dialog).
    try:
        for app in (script_engine.online.create_online_application(),):
            if app is not None and getattr(app, 'is_logged_in', False):
                app.logout()
                print("DEBUG: flush_editor_views: logged out of the device so the project can close.")
    except Exception as lo_err:
        print("DEBUG: flush_editor_views: logout skipped/failed (continuing): %s" % lo_err)

    primary_project.close()
    print("DEBUG: flush_editor_views: project closed to dispose editor views: %s" % project_path)

    # CODESYS persists the window layout (open editors) in the per-user
    # sidecar "<Project>-<user>-<machine>.opt" and RESTORES it on open --
    # so a close/reopen (or even a full IDE restart) brings all views back.
    # Delete the per-user .opt (pure UI state, regenerates); keep AllUsers.
    try:
        proj_dir = os.path.dirname(project_path)
        base = os.path.splitext(os.path.basename(project_path))[0]
        for fn in os.listdir(proj_dir):
            if fn.startswith(base + "-") and fn.endswith(".opt") and not fn.endswith("-AllUsers.opt"):
                os.remove(os.path.join(proj_dir, fn))
                print("DEBUG: flush_editor_views: deleted window-layout sidecar: %s" % fn)
    except Exception as opt_err:
        print("WARN: flush_editor_views: could not delete .opt sidecar: %s" % opt_err)

    reopened = script_engine.projects.open(project_path)
    print("DEBUG: flush_editor_views: project reopened: %s" % reopened.path)
    print("SCRIPT_SUCCESS: Editor views flushed (project close/reopen).")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error flushing editor views: %s\n%s" % (e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
