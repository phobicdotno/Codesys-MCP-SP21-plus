import sys, scriptengine as script_engine, os, traceback

TASK_NAME = "{TASK_NAME}"

try:
    print("DEBUG: create_task script: Task='%s', Project='%s'" % (TASK_NAME, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)
    if not TASK_NAME:
        raise ValueError("Task name empty.")

    # Multi-device projects: search the ACTIVE application first, then the
    # whole project.
    task_config = None
    _scopes = []
    try:
        _app = primary_project.active_application
        if _app is not None:
            _scopes.append(_app)
    except Exception:
        pass
    _scopes.append(primary_project)
    for _scope in _scopes:
        for child in _scope.get_children(True):
            if hasattr(child, 'is_task_configuration') and child.is_task_configuration:
                task_config = child
                break
        if task_config is not None:
            break
    if task_config is None:
        raise RuntimeError("No Task Configuration object found in project.")

    # Refuse duplicates -- create_task would either fail or create 'Name_1'.
    for t in task_config.get_children(False):
        if hasattr(t, 'is_task') and t.is_task and getattr(t, 'get_name', lambda: '')() == TASK_NAME:
            raise ValueError("Task '%s' already exists." % TASK_NAME)

    task = task_config.create_task(TASK_NAME)
    primary_project.save()

    print("Task: %s" % TASK_NAME)
    print("SCRIPT_SUCCESS: Task created. Project saved. Use configure_task to set kind/priority/interval, add_pou_to_task to add POUs.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error creating task '%s' in project %s: %s\n%s" % (
        TASK_NAME, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
