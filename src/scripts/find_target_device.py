# find_target_device: locate the PLC device object in a primary project.
#
# We define "target device" as the first ScriptDeviceObject in the project
# tree whose get_gateway() returns a non-empty Guid AND get_address()
# returns a non-empty router address. That excludes:
#   - Gateway nodes (DeviceTrackingMode.Gateway) which don't have a route
#     of their own,
#   - Placeholder/Dummy entries (no gateway configured).
#
# Most projects have exactly one PLC device. If a project has several, the
# caller can iterate find_all_target_devices() and pick by name.

def _is_device(obj):
    try:
        return bool(getattr(obj, 'is_device', False))
    except Exception:
        return False


def _device_has_route(dev):
    """True if the device has BOTH a gateway and an address configured."""
    try:
        gw = dev.get_gateway()
        addr = dev.get_address()
    except Exception:
        return False
    if gw is None:
        return False
    # ScriptGateway returns a Guid object; str() on an empty Guid is
    # "00000000-0000-0000-0000-000000000000". Treat that as no-route.
    gw_str = str(gw)
    if not gw_str or gw_str == '00000000-0000-0000-0000-000000000000':
        return False
    if not addr or not str(addr).strip():
        return False
    return True


def find_all_target_devices(primary_project):
    """Walk the project and return every device with a configured route."""
    out = []
    try:
        children = primary_project.get_children(True)
    except Exception:
        children = []
    for c in children:
        if _is_device(c) and _device_has_route(c):
            out.append(c)
    return out


def _device_hosting_active_application(primary_project, devices):
    """In a multi-device project, the routed device whose subtree holds the
    project's active application (or None if it cannot be determined)."""
    try:
        node = primary_project.active_application
    except Exception:
        return None
    guard = 0
    try:
        while node is not None and guard < 32 and not hasattr(node, 'active_application'):
            guard += 1
            if _is_device(node):
                for d in devices:
                    try:
                        if str(d.guid) == str(node.guid):
                            return d
                    except Exception:
                        pass
                return None
            node = node.parent
    except Exception:
        return None
    return None


def find_target_device(primary_project):
    """Return the routed device to talk to, or raise. With one routed device
    that is it; with several (multi-device project) the device hosting the
    active application wins, falling back to the first routed device."""
    devices = find_all_target_devices(primary_project)
    if not devices:
        raise RuntimeError(
            "No PLC device with a configured gateway+address found in project. "
            "Open the device's Communication Settings in the IDE and set "
            "Gateway + Device Address before retrying."
        )
    if len(devices) > 1:
        preferred = _device_hosting_active_application(primary_project, devices)
        if preferred is not None:
            try:
                print("DEBUG: find_target_device: %d routed devices; using '%s' (hosts the active application)" % (len(devices), preferred.get_name()))
            except Exception:
                pass
            return preferred
        print("DEBUG: find_target_device: %d routed devices; active application's device not resolved - using the first" % len(devices))
    return devices[0]


def device_summary(dev):
    """Plain-dict snapshot of a device for JSON emission. ASCII-safe."""
    info = {
        "name": "",
        "gateway_guid": "",
        "address": "",
        "scanned_device_name": "",
        "scanned_target_id": "",
        "scanned_target_name": "",
        "scanned_ip_address_and_port": "",
    }
    try:
        n = dev.get_name() if hasattr(dev, 'get_name') else None
        if n:
            info["name"] = str(n)
    except Exception:
        pass
    try:
        gw = dev.get_gateway()
        if gw is not None:
            info["gateway_guid"] = str(gw)
    except Exception:
        pass
    try:
        a = dev.get_address()
        if a is not None:
            info["address"] = str(a)
    except Exception:
        pass
    for prop in ("scanned_device_name", "scanned_target_id",
                 "scanned_target_name", "scanned_ip_address_and_port"):
        try:
            v = getattr(dev, prop, None)
            if v is not None:
                info[prop] = str(v)
        except Exception:
            pass
    return info
