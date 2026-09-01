import sys, scriptengine as script_engine, os, traceback

try:
    print("DEBUG: check_online_change script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)

    target_app = None
    try:
        target_app = primary_project.active_application
    except Exception as e:
        print("WARN: Could not get active application: %s" % e)
    if not target_app:
        raise RuntimeError("No active application found in project.")
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    if not hasattr(target_app, 'is_online_change_possible'):
        raise TypeError("is_online_change_possible is not available on this SP (needs 3.5.10.0+).")
    # Property on SP21 (returns bool directly); method on the SPs the stub
    # documents. Handle both.
    possible = target_app.is_online_change_possible
    if callable(possible):
        possible = possible()

    print("Application: %s" % app_name)
    print("Online Change Possible: %s" % possible)
    print("SCRIPT_SUCCESS: Online change check done.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error checking online change for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
