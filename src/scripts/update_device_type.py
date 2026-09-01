# update_device_type: in-place change of a project's top-level PLC device
# type, preserving the Application / POU / library subtree underneath.
# Wraps ScriptObject.update(device_id) per the documented CODESYS API
# (see forge.codesys.com/tol/scripting/snippets/20/).
#
# Inputs (template-substituted by Node):
#   {PROJECT_FILE_PATH}    -- absolute path to the .project file
#   {DEVICE_PATH}          -- '/'-separated path under the project root to the
#                             device to update (e.g. 'MainPLC'). Empty = pick
#                             the first device with a configured gateway+address
#                             via the find_target_device helper.
#   {TARGET_NAME}          -- substring of the target device display name
#                             (e.g. 'CODESYS Control for Raspberry Pi MC SL').
#                             Required.
#   {TARGET_VERSION}       -- optional exact version string (e.g. '4.13.0.0').
#                             Empty = highest-version match wins.
#
# This script does NOT fall back to remove()+add() when update() raises. The
# subtree the user wants to keep would be destroyed. Surfacing the raise is
# correct.

import sys
import traceback

PROJECT_FILE_PATH = r'{PROJECT_FILE_PATH}'
DEVICE_PATH = '{DEVICE_PATH}'
TARGET_NAME = '{TARGET_NAME}'
TARGET_VERSION = '{TARGET_VERSION}'


def _resolve_device_by_name(name, version):
    """Look up the device repository for a device whose display name
    matches `name` (substring) and optionally an exact `version`. Returns
    the highest-version match (or the version match if specified), or None.
    """
    repo = None
    try:
        repo = script_engine.device_repository
    except Exception as e:
        print("DEBUG: script_engine.device_repository unavailable: %s" % e)
    if repo is None:
        try:
            repo = device_repository  # noqa: F821 -- builtin if injected
        except NameError:
            print("DEBUG: device_repository builtin not in scope either.")
            return None
    try:
        candidates = repo.get_all_devices(name, None)
    except Exception as e:
        print("DEBUG: device_repository.get_all_devices(name, None) failed: %s" % e)
        return None
    if not candidates:
        return None

    def _version_key(dev):
        try:
            v = dev.device_id.version
        except Exception:
            return (0,)
        try:
            return tuple(int(p) for p in str(v).split('.'))
        except Exception:
            return (str(v),)

    if version:
        for d in candidates:
            try:
                if str(d.device_id.version) == version:
                    return d
            except Exception:
                continue
        return None

    best = None
    best_key = None
    for d in candidates:
        try:
            d_name = d.device_info.name
        except Exception:
            d_name = '?'
        k = _version_key(d)
        print("DEBUG: candidate device: name='%s', version=%s" % (d_name, k))
        if best is None or k > best_key:
            best = d
            best_key = k
    return best


def _is_device(obj):
    try:
        return bool(getattr(obj, 'is_device', False))
    except Exception:
        return False


def _find_device_by_path(project, path):
    """Walk '/'-separated `path` from project root, matching child names
    (case-insensitive on the final segment). Returns the ScriptObject or None.
    """
    segments = [s for s in path.replace('\\', '/').split('/') if s]
    if not segments:
        return None
    current = project
    for seg in segments:
        try:
            children = current.get_children(False)
        except Exception:
            children = []
        match = None
        for c in children:
            try:
                cn = c.get_name()
            except Exception:
                cn = ''
            if cn == seg or cn.lower() == seg.lower():
                match = c
                break
        if match is None:
            return None
        current = match
    return current


def _find_first_routed_device(project):
    """Fallback when no DEVICE_PATH is supplied: walk the whole project tree
    and return the first device that has a configured gateway+address. The
    intent is 'the PLC the user actually deploys to', which is almost always
    the top-level device on every MR project."""
    try:
        children = project.get_children(True)
    except Exception:
        children = []
    for c in children:
        if not _is_device(c):
            continue
        try:
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
    return None


def _routed_device_of_active_application(project):
    """Multi-device projects: the routed device (gateway+address) whose
    subtree holds the ACTIVE application, or None."""
    try:
        node = project.active_application
    except Exception:
        return None
    guard = 0
    while node is not None and guard < 32 and not hasattr(node, 'active_application'):
        guard += 1
        if _is_device(node):
            try:
                gw = node.get_gateway()
                addr = node.get_address()
            except Exception:
                return None
            if gw is None:
                return None
            gw_str = str(gw)
            if not gw_str or gw_str == '00000000-0000-0000-0000-000000000000':
                return None
            if not addr or not str(addr).strip():
                return None
            return node
        try:
            node = node.parent
        except Exception:
            return None
    return None

def _find_any_top_level_device(project):
    """Final fallback: first direct child of the project that is a device,
    regardless of gateway/address state. Used when the project hasn't been
    wired up yet (fresh from a template, for example)."""
    try:
        children = project.get_children(False)
    except Exception:
        children = []
    for c in children:
        if _is_device(c):
            return c
    return None


try:
    suppression_set = False
    try:
        from scriptengine import PromptHandling
        script_engine.system.prompt_handling = PromptHandling.NONE
        suppression_set = True
        print("DEBUG: system.prompt_handling = PromptHandling.NONE (suppress).")
    except Exception as e:
        print("DEBUG: could not set system.prompt_handling = PromptHandling.NONE: %s" % e)
    if not suppression_set:
        try:
            script_engine.system.prompt_handling = 0
            suppression_set = True
            print("DEBUG: system.prompt_handling = 0 (suppress, int fallback).")
        except Exception as e:
            print("DEBUG: int-literal prompt_handling = 0 also failed: %s" % e)

    print("DEBUG: update_device_type:")
    print("DEBUG:   Project        = %s" % PROJECT_FILE_PATH)
    print("DEBUG:   Device path    = %s" % (DEVICE_PATH or '<auto: first routed device>'))
    print("DEBUG:   Target name    = %s" % TARGET_NAME)
    print("DEBUG:   Target version = %s" % (TARGET_VERSION or '<latest>'))

    if not TARGET_NAME:
        msg = ("targetDeviceName is required (substring of the device "
               "repository entry's display name, e.g. 'CODESYS Control for "
               "Raspberry Pi MC SL').")
        print("ERROR: %s" % msg)
        print("SCRIPT_ERROR: %s" % msg)
        sys.exit(1)

    # ensure_project_open helper is included by the TS caller, so the project
    # is already open by the time this script runs.
    project = script_engine.projects.primary
    if 'apply_application_selection' in globals():
        apply_application_selection(project)
    if project is None:
        msg = "No primary project open -- ensure_project_open should have opened it."
        print("ERROR: %s" % msg)
        print("SCRIPT_ERROR: %s" % msg)
        sys.exit(1)

    if DEVICE_PATH:
        target_dev = _find_device_by_path(project, DEVICE_PATH)
        if target_dev is None:
            msg = ("Device path '%s' not found in project. Use forward slashes "
                   "and match the device names as shown in the navigator." % DEVICE_PATH)
            print("ERROR: %s" % msg)
            print("SCRIPT_ERROR: %s" % msg)
            sys.exit(1)
        if not _is_device(target_dev):
            msg = ("Object at '%s' is not a device. update_device_type only "
                   "operates on device-typed ScriptObjects." % DEVICE_PATH)
            print("ERROR: %s" % msg)
            print("SCRIPT_ERROR: %s" % msg)
            sys.exit(1)
    else:
        target_dev = _routed_device_of_active_application(project) or _find_first_routed_device(project)
        if target_dev is None:
            target_dev = _find_any_top_level_device(project)
        if target_dev is None:
            msg = ("No device found in project to update. Either the project "
                   "is empty, or pass an explicit devicePath.")
            print("ERROR: %s" % msg)
            print("SCRIPT_ERROR: %s" % msg)
            sys.exit(1)

    try:
        existing_name = target_dev.get_name()
    except Exception:
        existing_name = '<unknown>'

    new_device = _resolve_device_by_name(TARGET_NAME, TARGET_VERSION)
    if new_device is None:
        if TARGET_VERSION:
            msg = ("No device matching name~='%s' AND version='%s' in the "
                   "device repository. Open Tools > Device Repository to "
                   "confirm the exact name + available versions."
                   % (TARGET_NAME, TARGET_VERSION))
        else:
            msg = ("No device matching name~='%s' in the device repository. "
                   "Open Tools > Device Repository to confirm the exact name."
                   % TARGET_NAME)
        print("ERROR: %s" % msg)
        print("SCRIPT_ERROR: %s" % msg)
        sys.exit(1)

    try:
        new_dev_id = new_device.device_id
        new_dev_info = new_device.device_info
        new_name = new_dev_info.name
    except Exception as e:
        msg = ("Resolved device for '%s' is missing device_id/device_info: %s"
               % (TARGET_NAME, e))
        print("ERROR: %s" % msg)
        print("SCRIPT_ERROR: %s" % msg)
        sys.exit(1)

    print("DEBUG: Swapping device '%s' -> '%s' (type=%s id=%s version=%s)"
          % (existing_name, new_name, new_dev_id.type, new_dev_id.id, new_dev_id.version))

    # IN-PLACE update only. We intentionally do NOT fall back to remove+add:
    # that would destroy the Application/POU/library subtree the user is
    # specifically trying to preserve. If update() raises, surface the error.
    try:
        target_dev.update(new_dev_id)
    except Exception as e:
        detailed = traceback.format_exc()
        msg = ("ScriptObject.update(device_id) failed for '%s' -> '%s': %s\n"
               "%s\n"
               "This usually means the target device family cannot be swapped "
               "in-place from the current device kind (e.g. cross-vendor "
               "swaps). Inspect the device tree manually in the IDE: right-"
               "click the device > Update Device... and see what the dialog "
               "offers." % (existing_name, new_name, e, detailed))
        print("ERROR: %s" % msg)
        print("SCRIPT_ERROR: %s" % msg)
        sys.exit(1)

    try:
        project.save()
        print("DEBUG: Project saved.")
    except Exception as save_err:
        print("WARN: Project save after device update failed: %s" % save_err)

    print("Device '%s' updated to '%s' (version %s)."
          % (existing_name, new_name, new_dev_id.version))
    print("SCRIPT_SUCCESS: Device type updated in-place; subtree preserved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = ("Error in update_device_type: %s\n%s" % (e, detailed_error))
    print(error_message)
    print("SCRIPT_ERROR: %s" % e)
    sys.exit(1)
