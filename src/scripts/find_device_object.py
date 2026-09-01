# Helper: locate a device object by tree path, or the first device in the
# project when no path is given. Requires find_object_by_path (helper) when
# a path is used.

def find_device_object(primary_project, device_path):
    """Return a ScriptObject that is_device. device_path '' = first device."""
    if device_path:
        obj = find_object_by_path_robust(primary_project, device_path, "device")
        if not obj:
            raise ValueError("Device not found at path: %s" % device_path)
        if not (hasattr(obj, 'is_device') and obj.is_device):
            raise TypeError("Object at '%s' is not a device." % device_path)
        return obj
    # No path: prefer the device hosting the ACTIVE application (multi-device
    # projects), then fall back to the first device in the tree.
    try:
        node = primary_project.active_application
    except Exception:
        node = None
    guard = 0
    while node is not None and guard < 32 and not hasattr(node, 'active_application'):
        guard += 1
        if hasattr(node, 'is_device') and node.is_device:
            return node
        try:
            node = node.parent
        except Exception:
            node = None
    for child in primary_project.get_children(True):
        if hasattr(child, 'is_device') and child.is_device:
            return child
    raise RuntimeError("No device object found in project.")
