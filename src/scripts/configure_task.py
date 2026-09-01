import sys, scriptengine as script_engine, os, traceback

TASK_NAME = "{TASK_NAME}"
# Empty string = leave unchanged.
KIND = "{KIND}"
PRIORITY = "{PRIORITY}"
INTERVAL = "{INTERVAL}"
INTERVAL_UNIT = "{INTERVAL_UNIT}"
EVENT = {EVENT}

try:
    print("DEBUG: configure_task script: Task='%s', Kind='%s', Prio='%s', Interval='%s' %s, Event='%s', Project='%s'" % (
        TASK_NAME, KIND, PRIORITY, INTERVAL, INTERVAL_UNIT, EVENT, PROJECT_FILE_PATH))
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

    task = None
    for t in task_config.get_children(False):
        if hasattr(t, 'is_task') and t.is_task and getattr(t, 'get_name', lambda: '')() == TASK_NAME:
            task = t
            break
    if task is None:
        raise ValueError("Task '%s' not found. Use list_tasks to see existing tasks." % TASK_NAME)

    changed = []
    if KIND:
        kind_enum = getattr(script_engine, 'KindOfTask', None)
        if kind_enum is None:
            raise TypeError("scriptengine.KindOfTask is not available on this SP.")
        kind_map = {'cyclic': 'Cyclic', 'freewheeling': 'Freewheeling',
                    'event': 'Event', 'external_event': 'ExternalEvent', 'status': 'Status'}
        if KIND.lower() not in kind_map:
            raise ValueError("Invalid kind '%s'." % KIND)
        task.kind_of_task = getattr(kind_enum, kind_map[KIND.lower()])
        changed.append("kind=%s" % KIND)
    if PRIORITY:
        task.priority = PRIORITY
        changed.append("priority=%s" % PRIORITY)
    if INTERVAL:
        task.interval = INTERVAL
        changed.append("interval=%s" % INTERVAL)
    if INTERVAL_UNIT:
        task.interval_unit = INTERVAL_UNIT
        changed.append("interval_unit=%s" % INTERVAL_UNIT)
    if EVENT:
        task.event = EVENT
        changed.append("event=%s" % EVENT)

    if not changed:
        raise ValueError("Nothing to configure: all fields empty.")

    primary_project.save()
    print("Task: %s" % TASK_NAME)
    print("Changed: %s" % ", ".join(changed))
    print("SCRIPT_SUCCESS: Task configured. Project saved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error configuring task '%s' in project %s: %s\n%s" % (
        TASK_NAME, PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
