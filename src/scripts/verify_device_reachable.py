# verify_device_reachable: pre-flight check before connect/download.
#
# Locates the configured target device, runs a live network scan on its
# gateway, and reports whether the cached device address appears in the
# scan results. If it doesn't, the binding is stale and a rebind is needed
# before any login()/download() attempt.
#
# Returns a JSON block with:
#   reachable: bool
#   cached_address: str  (what the project thinks the device is at)
#   matched: list        (scan results whose address equals cached_address)
#   candidates: list     (scan results -- caller can pick one for rebind)

import sys, scriptengine as script_engine, os, traceback, json

PROJECT_FILE_PATH = r"{PROJECT_FILE_PATH}"


def _find_gateway(target_device):
    target_guid = str(target_device.get_gateway())
    online = getattr(script_engine, 'online', None)
    if online is None:
        raise RuntimeError("scriptengine.online is not available.")
    for gw in online.gateways:
        try:
            if str(gw.guid) == target_guid:
                return gw
        except Exception:
            continue
    raise RuntimeError("Device's gateway Guid %s is not in scriptengine.online.gateways." % target_guid)


def _describe(t):
    fields = ("device_name", "type_name", "vendor_name", "address", "parent_address")
    out = {}
    for f in fields:
        try:
            v = getattr(t, f, None)
            out[f] = "" if v is None else str(v)
        except Exception:
            out[f] = ""
    try:
        did = getattr(t, 'device_id', None)
        out["device_id"] = "" if did is None else str(did)
    except Exception:
        out["device_id"] = ""
    return out


try:
    print("DEBUG: verify_device_reachable: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)
    target = find_target_device(primary_project)
    cached_address = str(target.get_address())
    target_name = target.get_name() if hasattr(target, 'get_name') else ''
    print("DEBUG: target='%s' cached_address='%s'" % (target_name, cached_address))

    gw = _find_gateway(target)

    # Pre-flight should not freeze the IDE UI for the duration of a live
    # network scan. Try the gateway's cached scan first (instant, no UI
    # block). Only fall back to a live scan if no cache exists.
    items = []
    cache_used = False
    if hasattr(gw, 'get_cached_network_scan_result'):
        try:
            cached = gw.get_cached_network_scan_result()
            if cached is not None:
                items = [_describe(t) for t in cached]
                if items:
                    cache_used = True
                    print("DEBUG: using cached scan (%d items)" % len(items))
        except Exception as e:
            print("DEBUG: cached scan unavailable: %s" % e)

    if not items:
        print("DEBUG: no cached scan -- running live scan on gateway '%s'..." % gw.name)
        results = gw.perform_network_scan()
        items = [_describe(t) for t in (results or [])]

    matched = [i for i in items if i.get('address') == cached_address]

    reachable = len(matched) > 0

    print("### DEVICE_REACHABILITY_START ###")
    print(json.dumps({
        "reachable": bool(reachable),
        "cached_address": cached_address,
        "target_device_name": str(target_name) if target_name else '',
        "scanned_device_name": str(getattr(target, 'scanned_device_name', '') or ''),
        "matched": matched,
        "candidates": items,
        "candidate_count": len(items),
        "gateway_name": str(gw.name),
        "gateway_guid": str(gw.guid),
        "scan_source": "cache" if cache_used else "live",
    }, sort_keys=True))
    print("### DEVICE_REACHABILITY_END ###")

    print("SCRIPT_SUCCESS: verify_device_reachable completed.")
except Exception as e:
    print("SCRIPT_ERROR: %s: %s" % (type(e).__name__, e))
    traceback.print_exc()
    sys.exit(1)
