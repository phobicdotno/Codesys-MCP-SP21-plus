# scan_network_devices: drive a live network scan via the device's
# configured gateway and emit the list of discovered targets.
#
# API (per Stubs/scriptengine/ScriptOnline.pyi):
#   - scriptengine.online.gateways                        -> ScriptGateways (list)
#   - gateway.perform_network_scan()                      -> tuple[ScriptScanTargetDescription]
#   - ScriptScanTargetDescription.device_name / type_name / vendor_name /
#       device_id / address / parent_address
#
# Strategy:
#   - Locate the configured target device (helper find_target_device).
#   - Resolve its gateway by GUID from scriptengine.online.gateways.
#   - perform_network_scan() on that gateway (blocking, ~5-10s typical).
#   - Emit each result as a flat ASCII-safe JSON dict.
#
# If useCache=1, prefer get_cached_network_scan_result() and only fall
# back to a live scan when no cache exists. Useful for cheap polling.

import sys, scriptengine as script_engine, os, traceback, json

PROJECT_FILE_PATH = r"{PROJECT_FILE_PATH}"
USE_CACHE = "{USE_CACHE}" == '1'


def _find_gateway(target_device):
    """Match the device's gateway-Guid against the online.gateways list."""
    target_guid = str(target_device.get_gateway())
    online = getattr(script_engine, 'online', None)
    if online is None:
        raise RuntimeError("scriptengine.online is not available on this SP.")
    for gw in online.gateways:
        try:
            if str(gw.guid) == target_guid:
                return gw
        except Exception:
            continue
    # NVL-bench fix: when the device gateway GUID is not configured in this IDE profile
    # (fresh/headless profile), auto-register one under that GUID from env vars so online
    # tools work without manually picking a gateway in the IDE dropdown. Address/port are
    # NOT hard-coded -- set CODESYS_GATEWAY_ADDR (and optionally _PORT/_NAME).
    try:
        import os as _os
        _addr = _os.environ.get("CODESYS_GATEWAY_ADDR")
        if _addr:
            import System as _Sys
            _port = int(_os.environ.get("CODESYS_GATEWAY_PORT", "1217"))
            _gw = online.gateways.add_new_gateway(
                _os.environ.get("CODESYS_GATEWAY_NAME", "mcp-gateway"),
                {0: _addr, 1: _port}, None, _Sys.Guid(target_guid))
            print("DEBUG: auto-registered gateway %s:%d under guid %s" % (_addr, _port, target_guid))
            return _gw
    except Exception as _e:
        print("DEBUG: gateway auto-registration failed: %s" % _e)
    raise RuntimeError(
        "Device's configured gateway (Guid %s) is not in scriptengine.online.gateways. "
        "Open the IDE Gateway dropdown and pick a configured gateway." % target_guid
    )


def _describe(t):
    """ASCII-safe snapshot of a ScriptScanTargetDescription. Tolerant of
    missing fields (post-scan accessors may raise on partial results)."""
    fields = ("device_name", "type_name", "vendor_name", "address",
              "parent_address")
    out = {}
    for f in fields:
        try:
            v = getattr(t, f, None)
            out[f] = "" if v is None else str(v)
        except Exception:
            out[f] = ""
    # device_id is a DeviceID object -- coerce to str if present.
    try:
        did = getattr(t, 'device_id', None)
        out["device_id"] = "" if did is None else str(did)
    except Exception:
        out["device_id"] = ""
    return out


try:
    print("DEBUG: scan_network_devices: Project='%s', useCache=%s" % (
        PROJECT_FILE_PATH, USE_CACHE))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    target = find_target_device(primary_project)
    print("DEBUG: target device: %s @ %s (gateway=%s)" % (
        target.get_name() if hasattr(target, 'get_name') else '?',
        target.get_address(), target.get_gateway()))

    gw = _find_gateway(target)
    gw_name = str(getattr(gw, 'name', '?'))
    print("DEBUG: scanning on gateway '%s' (guid=%s)" % (gw_name, gw.guid))

    results = None
    cache_used = False
    if USE_CACHE and hasattr(gw, 'get_cached_network_scan_result'):
        try:
            results = gw.get_cached_network_scan_result()
            if results is not None and len(list(results)) > 0:
                cache_used = True
            else:
                results = None
        except Exception as e:
            print("DEBUG: cached scan unavailable: %s" % e)
            results = None

    if results is None:
        print("DEBUG: performing live network scan (this can take several seconds)...")
        results = gw.perform_network_scan()

    items = []
    for t in (results or []):
        items.append(_describe(t))

    cached_addr = str(target.get_address())
    matched = [i for i in items if i.get('address') == cached_addr]

    print("### NETWORK_SCAN_START ###")
    print(json.dumps({
        "gateway_name": gw_name,
        "gateway_guid": str(gw.guid),
        "cache_used": bool(cache_used),
        "target_device": device_summary(target),
        "results": items,
        "count": len(items),
        "matched_cached_address": len(matched),
    }, sort_keys=True))
    print("### NETWORK_SCAN_END ###")

    print("SCRIPT_SUCCESS: scan_network_devices completed.")
except Exception as e:
    print("SCRIPT_ERROR: %s: %s" % (type(e).__name__, e))
    traceback.print_exc()
    sys.exit(1)
