import sys, scriptengine as script_engine, os, shutil, time, traceback

# Placeholders
TEMPLATE_PROJECT_PATH = r'{TEMPLATE_PROJECT_PATH}'  # Path to Standard.project
PROJECT_FILE_PATH = r'{PROJECT_FILE_PATH}'          # Path for the new project (Target Path)
DEVICE_NAME = r'{DEVICE_NAME}'                       # Optional: substring of the device's display name (e.g. "CODESYS Control Win V3 x64").
                                                     # Empty -> keep the template's default device.

# RTFM (helpme-codesys.com + local SP22 P1 stubs):
#   - device_repository is injected into the scripting scope as a global
#     (`device_repository`) and exposes
#         get_all_devices(name: str, source: ScriptRepositorySource = None) -> tuple[ScriptDeviceDescription]
#     overload that returns devices whose display name contains `name`.
#     ScriptDeviceRepository.pyi line 377.
#   - ScriptDeviceDescription.device_id is the DeviceID triple (type, id,
#     version) that update()/plug() take. ScriptDeviceDescription.pyi line 43.
#   - ScriptDeviceObject.update(device: DeviceId, module: str = None)
#     replaces the device kind in-place, preserving children (Application,
#     tasks, libraries). ScriptDeviceObject.pyi line 145.
#   - ScriptDeviceObjectMarker.is_device tells us which child of the
#     project root is the PLC device. ScriptDeviceObject.pyi line 104.


def _find_device_in_project(project):
    """Walk the project's top-level children and return the first object
    whose is_device == True. Returns None if no PLC device is plugged."""
    try:
        children = project.get_children(False)
    except Exception as e:
        print("DEBUG: project.get_children failed: %s" % e)
        return None
    for child in children:
        try:
            if getattr(child, 'is_device', False):
                return child
        except Exception:
            continue
    return None


def _resolve_device_by_name(name):
    """Look up the device repository for a device whose display name
    matches `name` (substring match per get_all_devices(name, source)
    overload). Returns the highest-version match, or None."""
    try:
        repo = device_repository  # noqa: F821 -- injected by scriptengine
    except NameError:
        print("DEBUG: device_repository global not in scope.")
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


try:
    print("DEBUG: Python script create_project (copy from template):")
    print("DEBUG:   Template Source = %s" % TEMPLATE_PROJECT_PATH)
    print("DEBUG:   Target Path     = %s" % PROJECT_FILE_PATH)
    print("DEBUG:   Device Name     = %s" % (DEVICE_NAME or '<keep template default>'))
    if not PROJECT_FILE_PATH:
        raise ValueError("Target project file path empty.")
    if not TEMPLATE_PROJECT_PATH:
        raise ValueError("Template project file path empty.")
    if not os.path.exists(TEMPLATE_PROJECT_PATH):
        raise IOError("Template project file not found: %s" % TEMPLATE_PROJECT_PATH)

    target_dir = os.path.dirname(PROJECT_FILE_PATH)
    if not os.path.exists(target_dir):
        print("DEBUG: Creating target directory: %s" % target_dir)
        os.makedirs(target_dir)
    if os.path.exists(PROJECT_FILE_PATH):
        print("WARN: Target project file already exists, overwriting: %s" % PROJECT_FILE_PATH)

    print("DEBUG: Copying '%s' to '%s'..." % (TEMPLATE_PROJECT_PATH, PROJECT_FILE_PATH))
    shutil.copy2(TEMPLATE_PROJECT_PATH, PROJECT_FILE_PATH)
    print("DEBUG: File copy complete.")

    print("DEBUG: Opening the copied project: %s" % PROJECT_FILE_PATH)
    update_mode = script_engine.VersionUpdateFlags.NoUpdates | script_engine.VersionUpdateFlags.SilentMode
    project = script_engine.projects.open(PROJECT_FILE_PATH, update_flags=update_mode)
    print("DEBUG: script_engine.projects.open returned: %s" % project)
    if not project:
        msg = ("Failed to open project copy %s after copying template %s. "
               "projects.open returned None." % (PROJECT_FILE_PATH, TEMPLATE_PROJECT_PATH))
        print(msg)
        print("SCRIPT_ERROR: %s" % msg)
        sys.exit(1)

    print("DEBUG: Pausing briefly after open...")
    time.sleep(1.0)

    device_swapped = False
    swapped_to = None
    if DEVICE_NAME:
        new_device = _resolve_device_by_name(DEVICE_NAME)
        if new_device is None:
            msg = ("Device '%s' not found in the local device repository. "
                   "Open the IDE's Device Repository (Tools > Device Repository) "
                   "to confirm the exact display name, or pass an empty deviceName "
                   "to keep the template's default device." % DEVICE_NAME)
            print("ERROR: %s" % msg)
            print("SCRIPT_ERROR: %s" % msg)
            sys.exit(1)

        existing_device = _find_device_in_project(project)
        if existing_device is None:
            msg = ("Project '%s' has no top-level PLC device to swap; the "
                   "template may be empty or non-standard. Cannot apply "
                   "deviceName='%s'." % (PROJECT_FILE_PATH, DEVICE_NAME))
            print("ERROR: %s" % msg)
            print("SCRIPT_ERROR: %s" % msg)
            sys.exit(1)

        try:
            new_dev_id = new_device.device_id
            new_dev_info = new_device.device_info
            swapped_to = new_dev_info.name
        except Exception as e:
            msg = "Resolved device for '%s' is missing device_id/device_info: %s" % (DEVICE_NAME, e)
            print("ERROR: %s" % msg)
            print("SCRIPT_ERROR: %s" % msg)
            sys.exit(1)

        print("DEBUG: Swapping device '%s' -> '%s' (type=%s id=%s version=%s)" % (
            existing_device.get_name(),
            swapped_to,
            new_dev_id.type,
            new_dev_id.id,
            new_dev_id.version))
        try:
            existing_device.update(new_dev_id)
        except Exception as e:
            detailed = traceback.format_exc()
            msg = ("Device swap failed (existing.update(new_id) raised): %s\n%s"
                   % (e, detailed))
            print("ERROR: %s" % msg)
            print("SCRIPT_ERROR: %s" % msg)
            sys.exit(1)
        device_swapped = True
        print("DEBUG: Device swap succeeded.")

    try:
        print("DEBUG: Saving project after open%s..." % (
            " + device swap" if device_swapped else ""))
        project.save()
        print("DEBUG: Project save succeeded.")
    except Exception as save_err:
        print("WARN: Save after open failed: %s" % save_err)

    print("Project Created from Template Copy at: %s" % PROJECT_FILE_PATH)
    if device_swapped:
        print("Device set to: %s" % swapped_to)
    print("SCRIPT_SUCCESS: Project copied from template%s." % (
        " and device swapped" if device_swapped else ""))
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = ("Error creating project '%s' from template '%s': %s\n%s"
                     % (PROJECT_FILE_PATH, TEMPLATE_PROJECT_PATH, e, detailed_error))
    print(error_message)
    print("SCRIPT_ERROR: Error copying/opening template: %s" % e)
    sys.exit(1)
