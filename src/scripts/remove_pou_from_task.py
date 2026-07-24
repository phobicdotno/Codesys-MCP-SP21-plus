import sys, scriptengine as script_engine, os, traceback

# Removes a program POU from a task's call list in the project's Task
# Configuration. The ScriptEngine task.pous remove API is under-documented,
# so several call shapes are attempted and dir() is dumped on total failure.

TASK_NAME = "{TASK_NAME}"
POU_NAME = "{POU_NAME}"

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
    if not TASK_NAME: raise ValueError("Task name empty.")
    if not POU_NAME: raise ValueError("POU name empty.")

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

    pous = task.pous
    before = []
    try:
        for p in pous:
            before.append(str(p))
    except Exception:
        pass

    if POU_NAME not in before:
        raise ValueError("POU '%s' is not in task '%s' call list: %s" % (POU_NAME, TASK_NAME, ", ".join(before)))

    removed = False
    errors = []

    # remove(int index) FIRST: on SP21 both remove(name) and del pous[i] can
    # return without effect (no exception, entry persists -- observed Sea
    # Leopard 2026-07-24 after a program rename left a stale call). The int
    # overload of remove(index_or_name) is the variant that actually mutates.
    # Verification after save decides; nothing here is trusted.
    if not removed:
        try:
            pous.remove(before.index(POU_NAME)); removed = True
        except Exception as e:
            errors.append("remove(int): %s" % e)

    if not removed:
        try:
            del pous[before.index(POU_NAME)]; removed = True
        except Exception as e:
            errors.append("del[i]: %s" % e)

    if not removed:
        try:
            pous.remove(POU_NAME); removed = True
        except Exception as e:
            errors.append("remove(name): %s" % e)

    if not removed and hasattr(pous, 'remove_at'):
        try:
            pous.remove_at(before.index(POU_NAME)); removed = True
        except Exception as e:
            errors.append("remove_at(i): %s" % e)

    if not removed:
        try:
            del pous[before.index(POU_NAME)]; removed = True
        except Exception as e:
            errors.append("del[i]: %s" % e)

    if not removed:
        api = sorted([a for a in dir(pous) if not a.startswith('_')])
        raise TypeError("Could not remove POU '%s' from task '%s'. Tried: %s. pous API: %s" % (
            POU_NAME, TASK_NAME, "; ".join(errors), ", ".join(api)))

    primary_project.save()

    after = []
    try:
        for p in task.pous:
            after.append(str(p))
    except Exception:
        pass

    if POU_NAME in after:
        raise RuntimeError("Removal reported success but '%s' is STILL in task '%s' call list: %s" % (
            POU_NAME, TASK_NAME, ", ".join(after)))

    print("POU '%s' removed from task '%s'." % (POU_NAME, TASK_NAME))
    print("Task '%s' now calls: %s" % (TASK_NAME, ", ".join(after) if after else "(none)"))
    print("SCRIPT_SUCCESS: POU call removed from task.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error removing POU '%s' from task '%s': %s\n%s" % (POU_NAME, TASK_NAME, e, detailed_error)
    print(error_message); print("SCRIPT_ERROR: %s" % error_message); sys.exit(1)
