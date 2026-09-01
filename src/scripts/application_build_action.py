import sys, scriptengine as script_engine, os, traceback

ACTION = "{ACTION}"

try:
    print("DEBUG: application_build_action script: Action='%s', Project='%s'" % (ACTION, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)
    action = ACTION.lower().strip()
    if action not in ('generate_code', 'rebuild', 'clean'):
        raise ValueError("Invalid action '%s'. Must be 'generate_code', 'rebuild' or 'clean'." % ACTION)

    target_app = None
    try:
        target_app = primary_project.active_application
    except Exception as e:
        print("WARN: Could not get active application: %s. Searching..." % e)
    if not target_app:
        for child in primary_project.get_children(True):
            if hasattr(child, 'is_application') and child.is_application and hasattr(child, 'build'):
                target_app = child
                break
    if not target_app:
        raise RuntimeError("No application found in project.")
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    if not hasattr(target_app, action):
        raise TypeError("Application '%s' does not support %s()." % (app_name, action))
    print("DEBUG: Calling %s() on app '%s'..." % (action, app_name))
    getattr(target_app, action)()
    print("DEBUG: %s executed." % action)

    print("Action: %s" % action)
    print("Application: %s" % app_name)
    print("SCRIPT_SUCCESS: %s executed for application '%s'. Use get_compile_messages for details." % (action, app_name))
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error executing %s for project %s: %s\n%s" % (ACTION, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
