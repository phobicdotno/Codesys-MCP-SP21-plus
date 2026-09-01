# Helper: locate the Symbol Configuration ScriptObject in a project.
#
# Per the SP22 stub at
# C:\Program Files\CODESYS 3.5.22.10\CODESYS\ScriptLib\Stubs\scriptengine\ScriptSymbolConfigObject.pyi
# (and helpme-codesys.com/en/ScriptingEngine/ScriptSymbolConfigObject.html):
#
#   - Every ScriptObject is decorated with the marker
#     ScriptSymbolConfigObjectMarker, which exposes the @property
#     `is_symbol_config` -> bool.
#   - The Symbol Configuration object lives under an Application object;
#     a project may have multiple Applications, each with its own
#     Symbol Configuration. Recursive walk catches every one.
#
# Returns the FIRST symbol config object found (depth-first), or None.
# The callers that need ALL of them iterate via find_all_symbol_config_objects.


def find_all_symbol_config_objects(node, depth=0, max_depth=10):
    """Walk the project tree and return every ScriptObject whose
    is_symbol_config property is True. Depth-limited to defend against
    pathological / circular trees."""
    out = []
    if depth > max_depth:
        return out
    try:
        if hasattr(node, 'is_symbol_config'):
            try:
                isc = node.is_symbol_config
            except Exception:
                isc = False
            if isc:
                out.append(node)
    except Exception:
        pass
    try:
        children = node.get_children(False)
    except Exception:
        children = []
    for child in children:
        out.extend(find_all_symbol_config_objects(child, depth + 1, max_depth))
    return out


def find_symbol_config_object(primary_project):
    """Return the Symbol Configuration of the ACTIVE application when it has
    one (multi-device projects: one per application), else the first
    SymbolConfiguration ScriptObject anywhere in the project tree, or None."""
    try:
        app = primary_project.active_application
    except Exception:
        app = None
    if app is not None:
        in_app = find_all_symbol_config_objects(app)
        if in_app:
            return in_app[0]
    matches = find_all_symbol_config_objects(primary_project)
    if not matches:
        return None
    return matches[0]


def ensure_symbol_config(primary_project):
    """Return the first SymbolConfiguration object, raising RuntimeError
    if the project has none. Used by tools that mutate / read the
    symbol config -- create_symbol_config is the only tool that does
    NOT use this and instead creates the object."""
    obj = find_symbol_config_object(primary_project)
    if obj is None:
        raise RuntimeError(
            "No Symbol Configuration found in this project. "
            "Call create_symbol_config first to add one under the Application."
        )
    return obj


def symbol_config_path(primary_project, sc_obj):
    """Return a human-readable slash-separated path for the symbol config
    object, walking parents. Best-effort; returns just the object name on
    failure."""
    try:
        own_name = sc_obj.get_name()
    except Exception:
        own_name = '?'
    parts = [own_name]
    try:
        parent = sc_obj.parent
    except Exception:
        parent = None
    project_path = None
    try:
        project_path = primary_project.path
    except Exception:
        pass
    while parent is not None:
        try:
            if parent.path == project_path:
                # Reached the project root; stop -- don't include project file name.
                break
        except Exception:
            pass
        try:
            pname = parent.get_name()
        except Exception:
            pname = None
        if not pname:
            break
        parts.insert(0, pname)
        try:
            parent = parent.parent
        except Exception:
            break
    return '/'.join(parts)
