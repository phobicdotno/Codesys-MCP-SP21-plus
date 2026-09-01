# select_application: multi-device / multi-application project support.
#
# CODESYS keeps exactly ONE "active application" per project, and nearly
# every scripting call that builds, logs in, downloads or reads variables
# acts on it (project.active_application). In a project with several
# devices (e.g. a master and a slave PLC in one .project) the tools would
# otherwise always hit whichever application the IDE last activated.
#
# This helper is concatenated in front of tool scripts (like
# ensure_project_open) and provides:
#   enumerate_applications(project)      -> list of dicts (name, path, device, is_active, obj)
#   select_application(project, path)    -> resolves + activates, returns the app object
#   apply_application_selection(project) -> honours the APPLICATION_PATH tool argument
#
# Accepted forms for APPLICATION_PATH (all case-insensitive, / or \ separators):
#   - full path            'Master/Plc Logic/Application'
#   - trailing sub-path    'Plc Logic/Application' (must be unique)
#   - the device name      'Master'
#   - the application name 'Application' (only when unique)
#   - ''                   keep the current active application (no-op)
#
# ScriptProject.active_application has a setter since CODESYS 3.5.x
# (verified in the SP21 Patch 5 ScriptProject.pyi stubs).

import traceback


def _sa_name(obj):
    try:
        n = obj.get_name()
        return str(n) if n is not None else ''
    except Exception:
        return ''


def _sa_is_app(obj):
    try:
        return bool(getattr(obj, 'is_application', False))
    except Exception:
        return False


def _sa_is_device(obj):
    try:
        return bool(getattr(obj, 'is_device', False))
    except Exception:
        return False


def _sa_is_project(obj):
    # ScriptProject is the only node exposing active_application.
    return hasattr(obj, 'active_application')


def _sa_parent(obj):
    try:
        return obj.parent
    except Exception:
        return None


def application_full_path(app):
    """Build 'Device/Plc Logic/Application' by walking .parent up to the project."""
    parts = []
    node = app
    guard = 0
    while node is not None and guard < 32 and not _sa_is_project(node):
        guard += 1
        parts.append(_sa_name(node))
        node = _sa_parent(node)
    parts.reverse()
    return '/'.join(parts)


def device_of_application(app):
    """Return the device object hosting the application (walks up), or None."""
    node = app
    guard = 0
    while node is not None and guard < 32 and not _sa_is_project(node):
        guard += 1
        if _sa_is_device(node):
            return node
        node = _sa_parent(node)
    return None


def _sa_device_type(dev):
    if dev is None:
        return ''
    try:
        ident = dev.get_device_identification()
        parts = []
        for attr in ('type', 'id', 'version'):
            v = getattr(ident, attr, None)
            if v is not None:
                parts.append('%s=%s' % (attr, v))
        return ' '.join(parts)
    except Exception:
        return ''


def _sa_same_object(a, b):
    if a is None or b is None:
        return False
    try:
        return str(a.guid) == str(b.guid)
    except Exception:
        return a is b


def enumerate_applications(primary_project):
    """Every application in the project with its hosting device and active flag."""
    active = None
    try:
        active = primary_project.active_application
    except Exception as e:
        print("DEBUG: enumerate_applications: active_application raised: %s" % e)
    out = []
    try:
        children = primary_project.get_children(True)
    except Exception as e:
        print("WARN: enumerate_applications: get_children failed: %s" % e)
        children = []
    for c in children:
        if not _sa_is_app(c):
            continue
        dev = device_of_application(c)
        is_active = False
        try:
            is_active = bool(c.is_active_application)
        except Exception:
            is_active = _sa_same_object(c, active)
        out.append({
            'name': _sa_name(c),
            'path': application_full_path(c),
            'device': _sa_name(dev) if dev is not None else '',
            'device_type': _sa_device_type(dev),
            'is_active': is_active,
            'obj': c,
        })
    return out


def _sa_norm(p):
    return (p or '').replace('\\', '/').strip().strip('/').lower()


def _sa_describe(apps):
    if not apps:
        return '<none>'
    return ', '.join(["'%s'%s" % (a['path'], ' (active)' if a['is_active'] else '') for a in apps])


def select_application(primary_project, application_path):
    """Resolve application_path to exactly one application and make it the
    project's active application. Returns the application object. With an
    empty path returns the current active application (first found if the
    project reports none) without changing anything."""
    apps = enumerate_applications(primary_project)
    wanted = _sa_norm(application_path)
    if not wanted:
        for a in apps:
            if a['is_active']:
                return a['obj']
        return apps[0]['obj'] if apps else None

    matches = [a for a in apps if _sa_norm(a['path']) == wanted]
    if not matches:
        matches = [a for a in apps if _sa_norm(a['path']).endswith('/' + wanted)]
    if not matches:
        matches = [a for a in apps if a['device'].lower() == wanted]
    if not matches:
        matches = [a for a in apps if a['name'].lower() == wanted]

    if not matches:
        raise RuntimeError("Application '%s' not found in project. Available applications: %s"
                           % (application_path, _sa_describe(apps)))
    if len(matches) > 1:
        raise RuntimeError("Application '%s' is ambiguous (%d matches) - use the full path. Available applications: %s"
                           % (application_path, len(matches), _sa_describe(apps)))

    chosen = matches[0]
    if chosen['is_active']:
        print("DEBUG: select_application: '%s' is already the active application" % chosen['path'])
        return chosen['obj']
    try:
        primary_project.active_application = chosen['obj']
    except Exception as e:
        raise RuntimeError("Failed to set active application to '%s': %s\n%s"
                           % (chosen['path'], e, traceback.format_exc()))
    print("DEBUG: select_application: active application set to '%s'" % chosen['path'])
    return chosen['obj']


def apply_application_selection(primary_project):
    """Tool-script hook: activate APPLICATION_PATH when the tool passed one.
    Returns the selected application object, or None when no selection was
    requested. Scripts call it right after ensure_project_open, guarded by
    `if 'apply_application_selection' in globals()` so they keep working
    when this helper is not loaded."""
    try:
        requested = APPLICATION_PATH
    except NameError:
        return None
    if not requested or not str(requested).strip():
        return None
    return select_application(primary_project, str(requested))


# Placeholder for the tool argument (Python string literal, set by the server).
APPLICATION_PATH = {APPLICATION_PATH}
