import sys, scriptengine as script_engine, os, traceback

POU_NAME = "{POU_NAME}"
POU_TYPE_STR = "{POU_TYPE_STR}"
IMPL_LANGUAGE_STR = "{IMPL_LANGUAGE_STR}"
PARENT_PATH_REL = "{PARENT_PATH}"
DECLARATION_CONTENT = """{DECLARATION_CONTENT}"""
IMPLEMENTATION_CONTENT = """{IMPLEMENTATION_CONTENT}"""
SET_DECLARATION = {SET_DECLARATION}      # True only when the caller provided declarationCode
SET_IMPLEMENTATION = {SET_IMPLEMENTATION} # True only when the caller provided implementationCode

pou_type_map = {
    "Program": script_engine.PouType.Program,
    "FunctionBlock": script_engine.PouType.FunctionBlock,
    "Function": script_engine.PouType.Function
}
# Map common language names to ImplementationLanguages attributes if needed (optional, None usually works)
# lang_map = { "ST": script_engine.ImplementationLanguage.st, ... }

try:
    print("DEBUG: create_pou script: Name='%s', Type='%s', Lang='%s', ParentPath='%s', Project='%s'" % (POU_NAME, POU_TYPE_STR, IMPL_LANGUAGE_STR, PARENT_PATH_REL, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not POU_NAME: raise ValueError("POU name empty.")
    if not PARENT_PATH_REL: raise ValueError("Parent path empty.")

    # Resolve POU Type Enum
    pou_type_enum = pou_type_map.get(POU_TYPE_STR)
    if not pou_type_enum: raise ValueError("Invalid POU type string: %s. Use Program, FunctionBlock, or Function." % POU_TYPE_STR)

    # For common case where user just specified "Application", automatically try to find it
    if PARENT_PATH_REL == "Application":
        # Get project name from file path to build the likely full path
        project_name = os.path.splitext(os.path.basename(PROJECT_FILE_PATH))[0]
        potential_paths = [
            PARENT_PATH_REL,                                      # Original "Application"
            "%s.%s" % (project_name, PARENT_PATH_REL),           # "projectName.Application"
            "%s/%s" % (project_name, PARENT_PATH_REL),           # "projectName/Application"
            "PLCWinNT/Plc Logic/Application",                    # Common CODESYS structure
            "PLCWinNT.Plc Logic.Application",                    # Using dots instead
            project_name                                         # Just the project name itself might work
        ]

        print("DEBUG: Parent path is simply 'Application', trying several variants to find it")

        # Try each potential path until one works
        parent_object = None
        for path in potential_paths:
            print("DEBUG: Attempting to find parent with path: '%s'" % path)
            parent_candidate = find_object_by_path_robust(primary_project, path, "parent container")
            if parent_candidate:
                parent_object = parent_candidate
                print("DEBUG: Successfully found parent using path: '%s'" % path)
                break

        if not parent_object:
            # For diagnostics, try to get the application object directly as a fallback
            print("DEBUG: All path attempts failed. Trying to access application directly...")
            try:
                if hasattr(primary_project, 'active_application'):
                    app = primary_project.active_application
                    if app:
                        parent_object = app
                        print("DEBUG: Found application object directly: %s" % app.get_name())
                if not parent_object and hasattr(primary_project, 'find'):
                    apps = primary_project.find("Application", True)
                    if apps:
                        parent_object = apps[0]
                        print("DEBUG: Found application via search: %s" % parent_object.get_name())
            except Exception as e:
                print("ERROR: Direct application access also failed: %s" % e)
    else:
        # Use the provided path normally
        parent_object = find_object_by_path_robust(primary_project, PARENT_PATH_REL, "parent container")

    # Final check if parent was found
    if not parent_object:
        raise ValueError("Parent object not found for path: %s. Try using the full path like 'ProjectName.Application' or run get_project_structure first to see the correct structure." % PARENT_PATH_REL)

    parent_name = getattr(parent_object, 'get_name', lambda: str(parent_object))()
    print("DEBUG: Using parent object: %s (Type: %s)" % (parent_name, type(parent_object).__name__))

    # Check if parent object supports creating POUs (should implement ScriptIecLanguageObjectContainer)
    if not hasattr(parent_object, 'create_pou'):
        raise TypeError("Parent object '%s' of type %s does not support create_pou." % (parent_name, type(parent_object).__name__))

    # Set language GUID to None (let CODESYS default based on parent/settings)
    lang_guid = None
    print("DEBUG: Setting language to None (will use default).")
    # Example if mapping language string: lang_guid = lang_map.get(IMPL_LANGUAGE_STR, None)

    print("DEBUG: Calling parent_object.create_pou: Name='%s', Type=%s, Lang=%s" % (POU_NAME, pou_type_enum, lang_guid))

    # Call create_pou using keyword arguments
    new_pou = parent_object.create_pou(
        name=POU_NAME,
        type=pou_type_enum,
        language=lang_guid # Pass None
    )

    print("DEBUG: parent_object.create_pou returned: %s" % new_pou)
    if new_pou:
        new_pou_name = getattr(new_pou, 'get_name', lambda: POU_NAME)()
        print("DEBUG: POU object created: %s" % new_pou_name)

        # --- APPLY PROVIDED CODE (same API as set_pou_code: ScriptTextualObject
        #     textual_declaration / textual_implementation .replace()). If the
        #     caller provided code and it cannot be applied, FAIL LOUDLY --
        #     an empty POU that compiles clean and does nothing is a trap. ---
        if SET_DECLARATION:
            decl_obj = getattr(new_pou, 'textual_declaration', None)
            if decl_obj is not None and hasattr(decl_obj, 'replace'):
                decl_obj.replace(DECLARATION_CONTENT)
                print("DEBUG: Applied declarationCode to new POU.")
            else:
                error_message = "declarationCode was provided but POU '%s' has no writable textual_declaration (non-ST language?)." % new_pou_name
                print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
        if SET_IMPLEMENTATION:
            impl_obj = getattr(new_pou, 'textual_implementation', None)
            if impl_obj is not None and hasattr(impl_obj, 'replace'):
                impl_obj.replace(IMPLEMENTATION_CONTENT)
                print("DEBUG: Applied implementationCode to new POU.")
            else:
                error_message = "implementationCode was provided but POU '%s' has no writable textual_implementation (non-ST language?)." % new_pou_name
                print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)

        # --- SAVE THE PROJECT TO PERSIST THE NEW POU ---
        try:
            print("DEBUG: Saving Project...")
            primary_project.save() # Save the overall project file
            print("DEBUG: Project saved successfully after POU creation.")
        except Exception as save_err:
            print("ERROR: Failed to save Project after POU creation: %s" % save_err)
            detailed_error = traceback.format_exc()
            error_message = "Error saving Project after creating POU '%s': %s\\n%s" % (new_pou_name, save_err, detailed_error)
            print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
        # --- END SAVING ---

        print("POU Created: %s" % new_pou_name)
        print("Type: %s" % POU_TYPE_STR)
        print("Language: %s (Defaulted)" % IMPL_LANGUAGE_STR)
        print("Parent Path: %s" % PARENT_PATH_REL)
        print("SCRIPT_SUCCESS: POU created successfully.")
        sys.exit(0)
    else:
        error_message = "Failed to create POU '%s'. create_pou returned None." % POU_NAME
        print(error_message)
        print("SCRIPT_ERROR: %s" % error_message)
        sys.exit(1)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error creating POU '%s' in project '%s': %s\\n%s" % (POU_NAME, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: Error creating POU '%s': %s" % (POU_NAME, e))
    sys.exit(1)
