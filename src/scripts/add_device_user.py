# add_device_user: add a user to the PLC runtime's live User Management.
#
# Required for OPC UA authentication on SP16+ -- the OPC UA server reads
# its identity-token policies from the User Management database that
# lives ON THE DEVICE (not in CODESYSControl.cfg). Without at least one
# user, the server advertises an empty UserIdentityTokens list and
# UaExpert refuses to connect with BadIdentityTokenInvalid.
#
# API: ScriptOnlineDevice.create_live_user_management() -> ScriptLiveDeviceUserManagement
#      live_um.add_user(name, password, can_change_password=True, must_change_password=False)
# Requires an active online connection -- this script ensures the device
# session is open before calling.

import sys, scriptengine as script_engine, os, traceback

PROJECT_FILE_PATH = r"{PROJECT_FILE_PATH}"
USER_NAME = r"{USER_NAME}"
USER_PASSWORD = r"{USER_PASSWORD}"
CAN_CHANGE_PASSWORD = "{CAN_CHANGE_PASSWORD}" == '1'
MUST_CHANGE_PASSWORD = "{MUST_CHANGE_PASSWORD}" == '1'


def _find_target_device_inline(primary_project):
    """Same selection rule as find_target_device.find_target_device -
    inlined so this script doesn't depend on that helper being loaded.
    Multi-device projects: the routed device hosting the ACTIVE application
    wins; otherwise the first routed device."""
    try:
        node = primary_project.active_application
    except Exception:
        node = None
    guard = 0
    while node is not None and guard < 32 and not hasattr(node, 'active_application'):
        guard += 1
        if getattr(node, 'is_device', False):
            try:
                gw = node.get_gateway()
                addr = node.get_address()
                if gw is not None and str(gw) and str(gw) != '00000000-0000-0000-0000-000000000000' and addr and str(addr).strip():
                    return node
            except Exception:
                pass
            break
        try:
            node = node.parent
        except Exception:
            break
    for c in primary_project.get_children(True):
        try:
            if not getattr(c, 'is_device', False):
                continue
            gw = c.get_gateway()
            addr = c.get_address()
        except Exception:
            continue
        if gw is None:
            continue
        gw_str = str(gw)
        if not gw_str or gw_str == '00000000-0000-0000-0000-000000000000':
            continue
        if not addr or not str(addr).strip():
            continue
        return c
    raise RuntimeError("No PLC device with a configured gateway+address in project.")


try:
    if not USER_NAME:
        raise ValueError("USER_NAME is required.")
    print("DEBUG: add_device_user: Project='%s' user='%s'" % (PROJECT_FILE_PATH, USER_NAME))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)
    target = _find_target_device_inline(primary_project)
    print("DEBUG: target device: %s" % (target.get_name() if hasattr(target, 'get_name') else '?'))

    online = getattr(script_engine, 'online', None)
    if online is None or not hasattr(online, 'create_online_device'):
        raise RuntimeError("scriptengine.online.create_online_device unavailable on this SP.")
    online_device = online.create_online_device(target)

    try:
        if not (getattr(online_device, 'connected', False) or getattr(online_device, 'shared_connected', False)):
            online_device.connect()
            print("DEBUG: online_device.connect() succeeded")
    except Exception as e:
        raise RuntimeError("online_device.connect() failed: %s" % e)

    try:
        live_um = online_device.create_live_user_management()
    except Exception as e:
        raise RuntimeError(
            "create_live_user_management() failed (%s). "
            "Device may not support the live API (pre-SP16), or User Management "
            "needs initialization via the IDE first." % e
        )

    # Pull the device-side state into the local object. Without upload(),
    # live_um.users is empty even when the device has users -- the local
    # cache hasn't been populated.
    try:
        live_um.upload()
        print("DEBUG: live_um.upload() succeeded")
    except Exception as e:
        print("DEBUG: live_um.upload() failed: %s -- continuing with whatever local cache holds" % e)

    existing = []
    try:
        for u in live_um.users:
            try:
                existing.append(str(u.name))
            except Exception:
                pass
    except Exception as e:
        print("DEBUG: live_um.users read failed: %s -- continuing" % e)
    print("DEBUG: existing users: %r" % existing)

    action = None
    if USER_NAME in existing:
        try:
            live_um.set_user_password(USER_NAME, USER_PASSWORD)
            action = "updated"
            print("Updated password for existing user '%s'." % USER_NAME)
        except Exception as e:
            raise RuntimeError("set_user_password failed for '%s': %s" % (USER_NAME, e))
    else:
        try:
            live_um.add_user(USER_NAME, USER_PASSWORD, CAN_CHANGE_PASSWORD, MUST_CHANGE_PASSWORD)
            action = "added"
            print("Added user '%s' to device User Management." % USER_NAME)
        except Exception as e:
            # Defensive: the upload() should have populated existing, but
            # if it didn't (silent failure, stale cache), the device might
            # still reject add_user with "already existing". Fall back to
            # password update so the call still does something useful.
            msg = str(e)
            if 'already existing' in msg.lower() or 'already exists' in msg.lower():
                print("DEBUG: add_user reported user already exists -- falling back to set_user_password")
                try:
                    live_um.set_user_password(USER_NAME, USER_PASSWORD)
                    action = "updated-after-add-rejected"
                    print("Updated password for existing user '%s' (fallback)." % USER_NAME)
                except Exception as e2:
                    raise RuntimeError("add_user said exists, set_user_password also failed: %s" % e2)
            else:
                raise RuntimeError("add_user failed for '%s': %s" % (USER_NAME, e))

    # Final user list for confirmation.
    final = []
    try:
        for u in live_um.users:
            try:
                final.append(str(u.name))
            except Exception:
                pass
    except Exception:
        pass

    print("### DEVICE_USER_ADDED_START ###")
    import json
    print(json.dumps({
        "user": USER_NAME,
        "action": action,
        "users_before": existing,
        "users_after": final,
    }, sort_keys=True))
    print("### DEVICE_USER_ADDED_END ###")

    print("SCRIPT_SUCCESS: add_device_user completed.")
except Exception as e:
    detailed = traceback.format_exc()
    print("Error in add_device_user: %s\n%s" % (e, detailed))
    print("SCRIPT_ERROR: %s" % e)
    sys.exit(1)
