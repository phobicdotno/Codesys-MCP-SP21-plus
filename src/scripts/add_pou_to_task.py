import sys, scriptengine as script_engine, os, traceback

# Adds (appends) or inserts a program POU into a task's call list in the
# project's Task Configuration. Wraps the ScriptEngine task.pous.add / .insert
# API. INSERT_INDEX empty => append; otherwise insert at that 0-based index.

TASK_NAME = "{TASK_NAME}"
POU_NAME = "{POU_NAME}"
INSERT_INDEX = "{INSERT_INDEX}"

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

def find_task(tc, name):
    for t in _children(tc):
        if _name(t) == name:
            return t
    return None

try:
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)
    if not TASK_NAME: raise ValueError("Task name empty.")
    if not POU_NAME: raise ValueError("POU name empty.")

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

    task = find_task(tc, TASK_NAME)
    if task is None:
        names = [_name(t) for t in _children(tc)]
        raise ValueError("Task '%s' not found. Available tasks: %s" % (TASK_NAME, ", ".join(names)))

    if not hasattr(task, 'pous'):
        api = sorted([a for a in dir(task) if not a.startswith('_')])
        raise TypeError("Task '%s' exposes no 'pous' collection. Task API: %s" % (TASK_NAME, ", ".join(api)))

    if INSERT_INDEX.strip() == "":
        task.pous.add(POU_NAME)
        action = "appended"
    else:
        idx = int(INSERT_INDEX.strip())
        task.pous.insert(idx, POU_NAME)
        action = "inserted at index %d" % idx

    primary_project.save()

    calls = []
    try:
        for p in task.pous:
            calls.append(str(p))
    except Exception:
        pass

    print("POU '%s' %s in task '%s'." % (POU_NAME, action, TASK_NAME))
    print("Task '%s' now calls: %s" % (TASK_NAME, ", ".join(calls)))
    print("SCRIPT_SUCCESS: POU call added to task.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error adding POU '%s' to task '%s': %s\n%s" % (POU_NAME, TASK_NAME, e, detailed_error)
    print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
