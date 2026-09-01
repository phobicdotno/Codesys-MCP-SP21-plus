import sys, scriptengine as script_engine, os, traceback

DUT_NAME = "{DUT_NAME}"
DUT_TYPE_STR = "{DUT_TYPE_STR}"
PARENT_PATH_REL = "{PARENT_PATH}"

try:
    print("DEBUG: create_dut script: Name='%s', DutType='%s', ParentPath='%s', Project='%s'" % (DUT_NAME, DUT_TYPE_STR, PARENT_PATH_REL, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)
    if not DUT_NAME: raise ValueError("DUT name empty.")
    if not PARENT_PATH_REL: raise ValueError("Parent path empty.")

    # Map DUT type string to enum
    dut_type_enum = None
    dut_type_lower = DUT_TYPE_STR.lower()

    # Try scriptengine.DutType enum first
    if hasattr(script_engine, 'DutType'):
        dut_type_class = script_engine.DutType
        type_map = {
            'structure': 'Structure',
            'struct': 'Structure',
            'enumeration': 'Enumeration',
            'enum': 'Enumeration',
            'union': 'Union',
            'alias': 'Alias',
        }
        mapped_name = type_map.get(dut_type_lower, DUT_TYPE_STR)
        if hasattr(dut_type_class, mapped_name):
            dut_type_enum = getattr(dut_type_class, mapped_name)
            print("DEBUG: Resolved DUT type enum: %s -> %s" % (DUT_TYPE_STR, dut_type_enum))
        else:
            # Try lowercase/uppercase variants
            for attr_name in dir(dut_type_class):
                if attr_name.lower() == mapped_name.lower():
                    dut_type_enum = getattr(dut_type_class, attr_name)
                    print("DEBUG: Resolved DUT type enum (case-insensitive): %s -> %s" % (DUT_TYPE_STR, dut_type_enum))
                    break

    if dut_type_enum is None:
        raise ValueError("Could not resolve DUT type '%s'. Valid types: Structure, Enumeration, Union, Alias." % DUT_TYPE_STR)

    # Find parent object (same logic as create_pou)
    if PARENT_PATH_REL == "Application":
        project_name = os.path.splitext(os.path.basename(PROJECT_FILE_PATH))[0]
        potential_paths = [
            PARENT_PATH_REL,
            "%s.%s" % (project_name, PARENT_PATH_REL),
            "%s/%s" % (project_name, PARENT_PATH_REL),
        ]
        parent_object = None
        for path in potential_paths:
            parent_candidate = find_object_by_path_robust(primary_project, path, "parent container")
            if parent_candidate:
                parent_object = parent_candidate
                print("DEBUG: Found parent using path: '%s'" % path)
                break
        if not parent_object:
            try:
                if hasattr(primary_project, 'active_application'):
                    app = primary_project.active_application
                    if app:
                        parent_object = app
                        print("DEBUG: Found application directly: %s" % app.get_name())
                if not parent_object and hasattr(primary_project, 'find'):
                    apps = primary_project.find("Application", True)
                    if apps:
                        parent_object = apps[0]
            except Exception as e:
                print("ERROR: Direct application access failed: %s" % e)
    else:
        parent_object = find_object_by_path_robust(primary_project, PARENT_PATH_REL, "parent container")

    if not parent_object:
        raise ValueError("Parent object not found for path: %s" % PARENT_PATH_REL)

    parent_name = getattr(parent_object, 'get_name', lambda: str(parent_object))()
    print("DEBUG: Using parent object: %s" % parent_name)

    # Create the DUT
    if not hasattr(parent_object, 'create_dut'):
        raise TypeError("Parent object '%s' of type %s does not support create_dut." % (parent_name, type(parent_object).__name__))

    print("DEBUG: Calling create_dut: Name='%s', Type=%s" % (DUT_NAME, dut_type_enum))
    new_dut = parent_object.create_dut(name=DUT_NAME, type=dut_type_enum)

    if new_dut:
        new_dut_name = getattr(new_dut, 'get_name', lambda: DUT_NAME)()
        print("DEBUG: DUT object created: %s" % new_dut_name)

        try:
            print("DEBUG: Saving Project...")
            primary_project.save()
            print("DEBUG: Project saved successfully after DUT creation.")
        except Exception as save_err:
            print("ERROR: Failed to save Project after DUT creation: %s" % save_err)
            detailed_error = traceback.format_exc()
            error_message = "Error saving Project after creating DUT '%s': %s\n%s" % (DUT_NAME, save_err, detailed_error)
            print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)

        print("DUT Created: %s" % new_dut_name)
        print("Type: %s" % DUT_TYPE_STR)
        print("Parent Path: %s" % PARENT_PATH_REL)
        print("SCRIPT_SUCCESS: DUT created successfully.")
        sys.exit(0)
    else:
        error_message = "Failed to create DUT '%s'. create_dut returned None." % DUT_NAME
        print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error creating DUT '%s' in project '%s': %s\n%s" % (DUT_NAME, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
