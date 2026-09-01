import sys, scriptengine as script_engine, os, traceback

# Lists the tasks in the project's Task Configuration: each task's name,
# best-effort properties, and its ordered POU call list. Read-only.

def _children(obj):
    try:
        return list(obj.get_children(False))
    except Exception:
        return []

def _name(obj):
    try:
        return obj.get_name()
    except Exception:
        return ""

def _is_task_config(obj):
    try:
        if getattr(obj, 'is_task_configuration', False):
            return True
    except Exception:
        pass
    return _name(obj) == "Task Configuration"

def find_task_config(project):
    queue = _children(project)
    seen = 0
    while queue and seen < 5000:
        obj = queue.pop(0)
        seen += 1
        if _is_task_config(obj):
            return obj
        queue.extend(_children(obj))
    return None

try:
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)
    # Multi-device projects: use the Task Configuration of the ACTIVE
    # application (applicationPath / set_active_application); fall back
    # to the first one in the project.
    tc = None
    try:
        _app = primary_project.active_application
    except Exception:
        _app = None
    if _app is not None:
        tc = find_task_config(_app)
    if tc is None:
        tc = find_task_config(primary_project)
    if tc is None:
        raise ValueError("Task Configuration object not found in project.")

    print("### TASKS_START ###")
    print("Task Configuration: %s" % _name(tc))
    tasks = _children(tc)
    if not tasks:
        print("(no tasks)")
    for t in tasks:
        tname = _name(t)
        props = []
        for attr in ('priority', 'interval', 'cycle_time', 'task_type', 'type', 'watchdog_enabled'):
            try:
                if hasattr(t, attr):
                    val = getattr(t, attr)
                    if not callable(val):
                        props.append("%s=%s" % (attr, val))
            except Exception:
                pass
        calls = []
        try:
            if hasattr(t, 'pous'):
                for p in t.pous:
                    calls.append(str(p))
            else:
                calls = ["<no pous collection>"]
        except Exception as pe:
            calls = ["<pous read error: %s>" % pe]
        print("")
        print("Task: %s" % tname)
        if props:
            print("  Props: %s" % ", ".join(props))
        print("  POU calls (%d): %s" % (len(calls), ", ".join(calls) if calls else "(none)"))
    print("### TASKS_END ###")
    print("SCRIPT_SUCCESS: Listed tasks.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error listing tasks: %s\n%s" % (e, detailed_error)
    print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
