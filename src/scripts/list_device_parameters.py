import sys, scriptengine as script_engine, os, traceback

DEVICE_PATH = "{DEVICE_PATH}"

def _param_row(scope, param):
    pid = getattr(param, 'id', '?')
    name = getattr(param, 'name', None) or getattr(param, 'visible_name', '?')
    unit = ''
    try:
        unit = param.unit or ''
    except Exception:
        pass
    val = '<no value element>'
    try:
        if hasattr(param, 'value'):
            val = param.value
    except Exception as e:
        val = '<unreadable: %s>' % e
    return "%s\t%s\t%s\t%s\t%s" % (scope, pid, name, val, unit)

try:
    print("DEBUG: list_device_parameters script: Device='%s', Project='%s'" % (DEVICE_PATH, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    device = find_device_object(primary_project, DEVICE_PATH)
    dev_name = getattr(device, 'get_name', lambda: "Unknown")()

    count = 0
    print("### PARAMS_START ###")
    try:
        for param in (device.device_parameters or []):
            print(_param_row('device', param))
            count += 1
    except Exception as e:
        print("DEBUG: device_parameters walk failed: %s" % e)
    try:
        connectors = list(device.connectors or [])
    except Exception as e:
        print("DEBUG: connectors unavailable: %s" % e)
        connectors = []
    for i, conn in enumerate(connectors):
        scope = "connector[%d]:%s" % (i, getattr(conn, 'interface', '?'))
        try:
            for param in (getattr(conn, 'parameters', None) or []):
                print(_param_row(scope, param))
                count += 1
        except Exception as e:
            print("DEBUG: parameter walk failed for %s: %s" % (scope, e))
        # ScriptConnector exposes the host-side parameter set (e.g. the WAGO
        # "K-BUS Parameters" grid) only via host_parameters, not parameters.
        try:
            for param in (getattr(conn, 'host_parameters', None) or []):
                print(_param_row(scope + ':host', param))
                count += 1
        except Exception as e:
            print("DEBUG: host_parameter walk failed for %s: %s" % (scope, e))
    print("### PARAMS_END ###")

    print("Device: %s" % dev_name)
    print("Parameter Count: %d" % count)
    print("SCRIPT_SUCCESS: Listed %d device parameter(s)." % count)
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error listing device parameters in project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
