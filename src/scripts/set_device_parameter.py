import sys, scriptengine as script_engine, os, traceback

DEVICE_PATH = "{DEVICE_PATH}"
PARAM_NAME = {PARAM_NAME}
PARAM_ID = r"{PARAM_ID}"
NEW_VALUE = {NEW_VALUE}
# '' for NEW_VALUE_SENTINEL means read-only (get mode).
GET_ONLY = {GET_ONLY}

def _matches(param):
    if PARAM_ID:
        try:
            if str(getattr(param, 'id', None)) == PARAM_ID:
                return True
        except Exception:
            pass
    if PARAM_NAME:
        for attr in ('name', 'visible_name'):
            try:
                if str(getattr(param, attr, None)) == PARAM_NAME:
                    return True
            except Exception:
                pass
    return False

def _iter_params(device):
    try:
        for param in (device.device_parameters or []):
            yield 'device', param
    except Exception as e:
        print("DEBUG: device_parameters walk failed: %s" % e)
    try:
        connectors = list(device.connectors or [])
    except Exception:
        connectors = []
    for i, conn in enumerate(connectors):
        scope = "connector[%d]:%s" % (i, getattr(conn, 'interface', '?'))
        try:
            for param in (getattr(conn, 'parameters', None) or []):
                yield scope, param
        except Exception as e:
            print("DEBUG: parameter walk failed for %s: %s" % (scope, e))
        # ScriptConnector exposes the host-side parameter set (e.g. the WAGO
        # "K-BUS Parameters" grid) only via host_parameters, not parameters.
        try:
            for param in (getattr(conn, 'host_parameters', None) or []):
                yield scope + ':host', param
        except Exception as e:
            print("DEBUG: host_parameter walk failed for %s: %s" % (scope, e))

try:
    print("DEBUG: set_device_parameter script: Device='%s', Name='%s', Id='%s', GetOnly=%s, Project='%s'" % (
        DEVICE_PATH, PARAM_NAME, PARAM_ID, GET_ONLY, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not PARAM_NAME and not PARAM_ID:
        raise ValueError("Provide parameterName or parameterId.")
    device = find_device_object(primary_project, DEVICE_PATH)
    dev_name = getattr(device, 'get_name', lambda: "Unknown")()

    found_scope, found = None, None
    for scope, param in _iter_params(device):
        if _matches(param):
            found_scope, found = scope, param
            break
    if found is None:
        raise ValueError("Parameter not found (name='%s', id='%s') on device '%s'. Use list_device_parameters." % (
            PARAM_NAME, PARAM_ID, dev_name))

    name = getattr(found, 'name', None) or getattr(found, 'visible_name', '?')
    old_value = '<unreadable>'
    try:
        old_value = found.value
    except Exception as e:
        if GET_ONLY:
            raise RuntimeError("Parameter '%s' has no readable value element: %s" % (name, e))

    if GET_ONLY:
        print("Device: %s" % dev_name)
        print("Scope: %s" % found_scope)
        print("Parameter: %s" % name)
        print("Value: %s" % old_value)
        print("SCRIPT_SUCCESS: Parameter read.")
    else:
        found.value = NEW_VALUE
        primary_project.save()
        print("Device: %s" % dev_name)
        print("Scope: %s" % found_scope)
        print("Parameter: %s" % name)
        print("Old Value: %s" % old_value)
        print("New Value: %s" % NEW_VALUE)
        print("SCRIPT_SUCCESS: Parameter set. Project saved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error accessing device parameter in project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
