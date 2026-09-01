import sys, scriptengine as script_engine, os, traceback

ONLINE_MODE = {ONLINE_MODE}
OUTPUT_PATH = r"{OUTPUT_PATH}"

try:
    print("DEBUG: create_boot_application script: online=%s, output='%s', Project='%s'" % (
        ONLINE_MODE, OUTPUT_PATH, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)

    if ONLINE_MODE:
        # Creates the boot application directly ON the connected device.
        online_app, target_app = ensure_online_connection(primary_project)
        app_name = getattr(target_app, 'get_name', lambda: "Unknown")()
        ensure_logged_in(online_app)
        online_app.create_boot_application()
        print("Mode: online")
        print("Application: %s" % app_name)
        print("SCRIPT_SUCCESS: Boot application created on device.")
    else:
        # Offline: writes <output>.app next to the project (or given path).
        # Requires generated code (compile first).
        app = primary_project.active_application
        if app is None:
            raise RuntimeError("No active application in project.")
        app_name = getattr(app, 'get_name', lambda: "Unknown")()
        out = OUTPUT_PATH if OUTPUT_PATH else None
        app.create_boot_application(out)
        print("Mode: offline")
        print("Application: %s" % app_name)
        print("Output: %s" % (OUTPUT_PATH if OUTPUT_PATH else "<default: <application>.app next to project>"))
        print("SCRIPT_SUCCESS: Offline boot application file created.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error creating boot application for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
