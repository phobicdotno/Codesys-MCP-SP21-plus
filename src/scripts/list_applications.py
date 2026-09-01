import sys, scriptengine as script_engine, os, traceback, json

# Lists every application in the project (one per device in multi-device
# projects) together with its hosting device and whether it is the active
# application. Read-only. Requires the select_application helper.

try:
    print("DEBUG: list_applications script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    apps = enumerate_applications(primary_project)
    payload = []
    for a in apps:
        payload.append({
            'name': a['name'],
            'path': a['path'],
            'device': a['device'],
            'device_type': a['device_type'],
            'is_active': bool(a['is_active']),
        })
    print("### APPLICATIONS_START ###")
    print(json.dumps(payload))
    print("### APPLICATIONS_END ###")
    print("Applications: %d" % len(payload))
    print("SCRIPT_SUCCESS: list_applications complete.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error listing applications in project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
