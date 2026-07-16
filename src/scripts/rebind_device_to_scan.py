# rebind_device_to_scan: re-bind the configured device to a scan result
# (typically the same physical PLC at a new gateway address after a
# reboot / re-cable / DHCP change).
#
# Match rule (in priority order):
#   1. exact device_name match (case-insensitive)
#   2. exact device_id match
#   3. caller-supplied address override (MATCH_ADDRESS)
#   4. if exactly one candidate, pick it
#   5. otherwise: refuse and dump the candidate list
#
# Once matched, call device.set_gateway_and_address(gateway, address) and
# save the project so the rebind persists across CODESYS restarts.

import sys, scriptengine as script_engine, os, traceback, json

PROJECT_FILE_PATH = r"{PROJECT_FILE_PATH}"
MATCH_NAME = r"{MATCH_NAME}"        # optional override
MATCH_DEVICE_ID = r"{MATCH_DEVICE_ID}"  # optional override
MATCH_ADDRESS = r"{MATCH_ADDRESS}"  # optional override -- skip scan match


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


def _pick_candidate(items, want_name, want_id, want_address):
    # 1. caller forced an address -- no scan match needed
    if want_address:
        return {"address": want_address, "device_name": "(forced)"}, "forced-address"
    # 2. by name
    if want_name:
        wn = want_name.lower()
        hits = [i for i in items if i.get('device_name', '').lower() == wn]
        if len(hits) == 1:
            return hits[0], "by-name"
        if len(hits) > 1:
            return None, "ambiguous-name"
    # 3. by device_id
    if want_id:
        hits = [i for i in items if i.get('device_id') == want_id]
        if len(hits) == 1:
            return hits[0], "by-device-id"
        if len(hits) > 1:
            return None, "ambiguous-device-id"
    # 4. single candidate
    if len(items) == 1:
        return items[0], "only-candidate"
    return None, "no-match"


try:
    print("DEBUG: rebind_device_to_scan: Project='%s' name='%s' id='%s' addr='%s'" % (
        PROJECT_FILE_PATH, MATCH_NAME, MATCH_DEVICE_ID, MATCH_ADDRESS))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    target = find_target_device(primary_project)
    target_name = target.get_name() if hasattr(target, 'get_name') else ''
    cached_address = str(target.get_address())
    print("DEBUG: target='%s' cached_address='%s'" % (target_name, cached_address))

    gw = _find_gateway(target)
    items = []
    if not MATCH_ADDRESS:
        print("DEBUG: scanning gateway '%s'..." % gw.name)
        items = [_describe(t) for t in (gw.perform_network_scan() or [])]

    pick, reason = _pick_candidate(items, MATCH_NAME, MATCH_DEVICE_ID, MATCH_ADDRESS)

    if pick is None:
        print("### REBIND_RESULT_START ###")
        print(json.dumps({
            "rebound": False,
            "reason": reason,
            "cached_address": cached_address,
            "candidates": items,
            "candidate_count": len(items),
        }, sort_keys=True))
        print("### REBIND_RESULT_END ###")
        print("SCRIPT_SUCCESS: rebind_device_to_scan completed (no rebind).")
        sys.exit(0)

    new_address = pick.get('address') or ''
    if not new_address:
        raise RuntimeError("Selected candidate has empty address: %r" % pick)

    # Always call set_gateway_and_address, even when the address didn't
    # change. The IDE's Select-Device + OK flow does the same -- it
    # re-applies the binding to refresh the device's scanned_* properties
    # and re-establish a live session, which login()/download() depend
    # on. Skipping when address matches leaves the binding stale.
    print("DEBUG: rebinding (cached='%s' new='%s' reason=%s)" % (cached_address, new_address, reason))
    # IP-form addresses (e.g. '127.0.0.1:11740' for an SSH-tunnelled PLC) are
    # not valid node addresses for set_gateway_and_address ("Invalid address
    # format"). Use set_gateway_and_ip_address (ScriptDeviceObject, since
    # 3.5.8.0) which takes "ip[:port]" and connects the block driver directly
    # by IP -- no UDP discovery needed.
    import re as _re
    if _re.match(r'^\d{1,3}(\.\d{1,3}){3}(:\d+)?$', new_address):
        print("DEBUG: IP-form address detected -> set_gateway_and_ip_address")
        target.set_gateway_and_ip_address(gw, new_address)
    else:
        target.set_gateway_and_address(gw, new_address)
    try:
        primary_project.save()
    except Exception as e:
        print("WARN: project.save() raised: %s -- rebind applied in-memory; flush manually." % e)

    print("### REBIND_RESULT_START ###")
    print(json.dumps({
        "rebound": True,
        "reason": reason,
        "old_address": cached_address,
        "new_address": new_address,
        "matched_candidate": pick,
    }, sort_keys=True))
    print("### REBIND_RESULT_END ###")
    print("SCRIPT_SUCCESS: rebind_device_to_scan completed.")
except Exception as e:
    print("SCRIPT_ERROR: %s: %s" % (type(e).__name__, e))
    traceback.print_exc()
    sys.exit(1)
