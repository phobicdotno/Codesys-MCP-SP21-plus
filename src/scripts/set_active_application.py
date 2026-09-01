import sys, scriptengine as script_engine, os, traceback, json

# Makes the given application the project's active application and saves
# the project so the choice persists (the active application is stored in
# the .project). Requires the select_application helper (APPLICATION_PATH).

try:
    print("DEBUG: set_active_application script: Project='%s', Application='%s'" % (PROJECT_FILE_PATH, APPLICATION_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not APPLICATION_PATH or not str(APPLICATION_PATH).strip():
        raise ValueError("applicationPath must not be empty. Use list_applications to see the candidates.")

    before = ''
    for a in enumerate_applications(primary_project):
        if a['is_active']:
            before = a['path']
            break

    chosen = select_application(primary_project, APPLICATION_PATH)
    after = application_full_path(chosen)

    try:
        primary_project.save()
        print("DEBUG: project.save() succeeded after activating '%s'." % after)
    except Exception as save_e:
        print("WARNING: project.save() raised %s - active application changed in memory only." % save_e)

    print("### ACTIVE_APPLICATION_START ###")
    print(json.dumps({'before': before, 'after': after, 'changed': before != after}))
    print("### ACTIVE_APPLICATION_END ###")
    print("Active application: %s -> %s" % (before or '<none>', after))
    print("SCRIPT_SUCCESS: set_active_application complete.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error setting active application in project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
