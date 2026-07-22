import sys, scriptengine as script_engine, os, traceback

IMPORT_PATH = r"{IMPORT_PATH}"
PARENT_OBJECT_PATH = r"{PARENT_OBJECT_PATH}"

try:
    print("DEBUG: import_native script: path='%s', parent='%s', Project='%s'" % (IMPORT_PATH, PARENT_OBJECT_PATH, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not IMPORT_PATH or not os.path.isfile(IMPORT_PATH):
        raise ValueError("Import file does not exist: %s" % IMPORT_PATH)

    if PARENT_OBJECT_PATH:
        # Import UNDER a specific object (ScriptObject.import_native, API >= 3.4.4.0).
        # Without this, project-level import lands at the PROJECT ROOT (the POU
        # pool, visible only in the POUs view) -- and CODESYS refuses to move
        # root-level objects into an application afterwards ("Cannot move X
        # from '<root>'"), so a wrong-level import is unrecoverable by script.
        parent_object = find_object_by_path_robust(primary_project, PARENT_OBJECT_PATH, "import parent")
        if parent_object is None:
            raise ValueError("Parent object not found at path: %s" % PARENT_OBJECT_PATH)
        result = parent_object.import_native(IMPORT_PATH)
    else:
        result = primary_project.import_native(IMPORT_PATH)
    primary_project.save()
    print("DEBUG: import_native + save OK")

    # NativeImportResult exposes imported_objects on most SPs; best-effort.
    try:
        imported = list(getattr(result, 'imported_objects', None) or [])
        print("Imported Objects: %d" % len(imported))
        for obj in imported[:50]:
            print("  - %s" % getattr(obj, 'get_name', lambda: '?')())
    except Exception as e:
        print("DEBUG: could not enumerate import result: %s" % e)

    print("Import Path: %s" % IMPORT_PATH)
    print("SCRIPT_SUCCESS: Native import completed. Project saved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error importing native file into project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
