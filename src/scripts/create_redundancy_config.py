import sys, scriptengine as script_engine, os, traceback, json

# create_redundancy_config: add (or update) the "Redundancy Configuration"
# object of an application and configure it without the IDE editor.
#
# The scripting API has no redundancy support. This script uses the
# Automation Platform API of RedundancyObject.plugin / RedundancyEditor.plugin
# (reflected from the SP21 P5 assemblies, plugin 4.3.0.0):
#   - object:   RedundancyObjectFactory -> RedundancyObject (type guid
#               756037c5-9627-47c1-8a26-39d1543fa569), settings in
#               IRedundancySettings (IpAddressPlc1FirstLink, PortFirstLink,
#               StandbyWaitTime, SyncWaitTime, AutoSyncEnabled, ...)
#   - PLC2:     a HIDDEN root device object "RedundancyDevice_<objectGuid>"
#               whose guid is IRedundancyObject.DeviceObjectGuid. The editor
#               creates it lazily (RedundancyEditor.GetDeviceObjectToRead) with
#               the device identification of the application's device via the
#               device object factory {84d12aa5-...} and create flag "2"
#               (hidden). A missing device makes every compile pop
#               "The object GUID '0000...' is not valid", so it is created here.
#   - Set Path PLC2: batch command "redundancy setactivepathplc2"
#               (SetActivePathPlc2Command.ExecuteBatch([objGuid, gatewayName,
#               scannedDeviceName])), non-interactive: scans the gateway and
#               binds the hidden device to the matching node.
#   - Write:    batch command "redundancy writesettings" (WriteSettingsCommand)
#               pushes the settings to BOTH runtimes over the online settings
#               service (component CmpRedundancy). Needs both PLCs reachable.
#               Verified 2026-09-16 on WAGO PFC200 750-8210 FW31: the runtime
#               stores them in /home/codesys_root/CODESYSControl.cfg (sections
#               [CmpRedundancyConnectionIP] + [CmpRedundancy]), NOT in the
#               eRUNTIME.cfg named by WAGO's FW26-era how-to, and the Write
#               also assigns PlcIdent 1/2. They apply after a runtime restart.

OBJECT_NAME = {OBJECT_NAME}
PARENT_PATH = {PARENT_PATH}
SETTINGS = json.loads({SETTINGS_JSON})
NON_REDUNDANT_PATHS = json.loads({NON_REDUNDANT_PATHS_JSON})
REDUNDANT_PATHS = json.loads({REDUNDANT_PATHS_JSON})
PLC2_GATEWAY = {PLC2_GATEWAY}
PLC2_DEVICE_NAME = {PLC2_DEVICE_NAME}
PLC2_ADDRESS = {PLC2_ADDRESS}
WRITE_SETTINGS = {WRITE_SETTINGS}

REDUNDANCY_OBJECT_TYPE = '_3S.CoDeSys.Redundancy.RedundancyObject'
REDUNDANCY_TYPE_GUID = '756037c5-9627-47c1-8a26-39d1543fa569'
DEVICE_OBJECT_FACTORY_GUID = '84d12aa5-3225-473b-9df6-18af40889bdf'
HIDDEN_DEVICE_FLAG = '2'

# IRedundancySettings property -> value kind
SETTING_KINDS = {
    'IpAddressPlc1FirstLink': 'str',
    'IpAddressPlc2FirstLink': 'str',
    'PortFirstLink': 'u16',
    'UseSecondLink': 'bool',
    'IpAddressPlc1SecondLink': 'str',
    'IpAddressPlc2SecondLink': 'str',
    'PortSecondLink': 'u16',
    'RedundancyTaskName': 'str',
    'StandbyWaitTime': 'u32',
    'SyncWaitTime': 'u32',
    'BootUpWaitTime': 'u32',
    'AutoSyncEnabled': 'bool',
    'DataSyncAlways': 'bool',
    'DebugMessages': 'bool',
    'EnableSyncTimeTrace': 'bool',
}


def _load_assembly(name):
    import clr
    import System
    for asm in System.AppDomain.CurrentDomain.GetAssemblies():
        if asm.GetName().Name == name:
            clr.AddReference(asm)
            return asm
    clr.AddReference(name)
    for asm in System.AppDomain.CurrentDomain.GetAssemblies():
        if asm.GetName().Name == name:
            return asm
    return None


def _coerce(kind, value):
    import System
    if kind == 'str':
        return str(value)
    if kind == 'bool':
        return bool(value)
    if kind == 'u16':
        return System.UInt16(int(value))
    if kind == 'u32':
        return System.UInt32(int(value))
    raise ValueError("unknown setting kind %s" % kind)


def _settings_dict(settings):
    out = {}
    for key in sorted(SETTING_KINDS.keys()):
        try:
            v = getattr(settings, key)
            if SETTING_KINDS[key] in ('u16', 'u32'):
                v = int(v)
            elif SETTING_KINDS[key] == 'bool':
                v = bool(v)
            else:
                v = str(v)
            out[key] = v
        except Exception as e:
            out[key] = 'unreadable: %s' % e
    return out


def _has_non_redundant_area(ro, obj_guid):
    try:
        return ro.GetNonRedundantArea(obj_guid) is not None
    except Exception:
        return False


def _find_redundancy_child(parent):
    for c in parent.get_children(False):
        try:
            if str(c.type).lower().strip('{}') == REDUNDANCY_TYPE_GUID:
                return c
        except Exception:
            pass
    return None


def _implements(type_obj, interface_name):
    try:
        for i in type_obj.GetInterfaces():
            if i.Name == interface_name:
                return True
    except Exception:
        pass
    return False


def _owning_device_guid(om, handle, object_guid):
    import System
    stub = om.GetMetaObjectStub(handle, object_guid)
    while stub.ParentObjectGuid != System.Guid.Empty:
        stub = om.GetMetaObjectStub(handle, stub.ParentObjectGuid)
        if _implements(stub.ObjectType, 'IDeviceObject'):
            return stub.ObjectGuid
    return None


def _ensure_hidden_device(om, handle, red_guid, device_guid):
    import System
    if om.ExistsObject(handle, device_guid):
        return False
    owner_guid = _owning_device_guid(om, handle, red_guid)
    if owner_guid is None:
        raise RuntimeError("No device above the redundancy object; cannot derive the PLC2 device identification")
    owner = om.GetObjectToRead(handle, owner_guid).Object
    devid = owner.DeviceIdentification
    factory = om.ObjectFactoryManager.GetFactory(System.Guid(DEVICE_OBJECT_FACTORY_GUID))
    if factory is None:
        raise RuntimeError("Device object factory %s not found" % DEVICE_OBJECT_FACTORY_GUID)
    args = System.Array[System.String]([str(devid.Type), str(devid.Id), str(devid.Version), '', HIDDEN_DEVICE_FLAG])
    dev = factory.Create(args)
    name = 'RedundancyDevice_' + str(red_guid)
    om.AddObject(handle, System.Guid.Empty, device_guid, dev, name, -1)
    print("DEBUG: created hidden PLC2 device '%s' guid=%s ident=%s/%s/%s" % (name, device_guid, devid.Type, devid.Id, devid.Version))
    return True


def _run_batch_command(type_name, arguments):
    import System
    asm = _load_assembly('RedundancyEditor.plugin')
    if asm is None:
        raise RuntimeError("RedundancyEditor.plugin is not loaded in this IDE (CODESYS Redundancy add-on missing?)")
    t = asm.GetType(type_name)
    if t is None:
        raise RuntimeError("Command type %s not found in %s" % (type_name, asm.FullName))
    cmd = System.Activator.CreateInstance(t)
    print("DEBUG: running batch '%s' %s" % (' '.join(list(cmd.BatchCommand)), arguments))
    cmd.ExecuteBatch(System.Array[System.String](arguments))


def _gateway_by_name(name):
    online_mgr = SystemInstances.OnlineMgr
    gateways = online_mgr.GetGateways()
    for g in gateways:
        if str(g.Name) == name:
            return g
    raise RuntimeError("Gateway '%s' not found. Configured gateways: %s" % (name, ', '.join([str(g.Name) for g in gateways])))


def _set_path_plc2_direct(handle, device_guid, gateway_name, identifier):
    """Bind PLC2 to an address instead of a scan result, for addresses a
    gateway scan cannot see (an SSH-tunnelled 127.0.0.1:port, for example).
    Calls SetActivePathPlc2Command.SetActivePath the way its own ExecuteBatch
    does, non-interactively and with no editor."""
    import System
    asm = _load_assembly('RedundancyEditor.plugin')
    if asm is None:
        raise RuntimeError("RedundancyEditor.plugin is not loaded in this IDE (CODESYS Redundancy add-on missing?)")
    t = asm.GetType('_3S.CoDeSys.Redundancy.SetActivePathPlc2Command')
    if t is None:
        raise RuntimeError("SetActivePathPlc2Command not found in %s" % asm.FullName)
    cmd = System.Activator.CreateInstance(t)
    gw = _gateway_by_name(gateway_name)
    # Both helpers are internal/private statics, so the lookup needs flags.
    from System.Reflection import BindingFlags
    flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance
    mode_mi = t.GetMethod('DetermineAddDeviceMode', flags)
    if mode_mi is None:
        raise RuntimeError("DetermineAddDeviceMode not found on SetActivePathPlc2Command")
    mode = mode_mi.Invoke(None if mode_mi.IsStatic else cmd, System.Array[System.Object]([identifier]))
    mi = t.GetMethod('SetActivePath', flags)
    if mi is None:
        raise RuntimeError("SetActivePath not found on SetActivePathPlc2Command")
    args = System.Array[System.Object]([None, False, True, handle, device_guid, gw.GatewayGuid, identifier, mode, '', None])
    print("DEBUG: SetActivePath(identifier='%s', gateway='%s', mode=%s)" % (identifier, gateway_name, mode))
    ok = mi.Invoke(None if mi.IsStatic else cmd, args)
    if not ok:
        raise RuntimeError("SetActivePath failed for '%s' via gateway '%s': %s" % (identifier, gateway_name, args[9]))


def _check_devices_reachable(om, handle, red_guid, device_guid):
    """Connect to PLC1 (the application's device) and PLC2 (the hidden
    device) the same way WriteSettingsCommand does, before running it."""
    plc2 = _plc2_path(om, handle, device_guid)
    if not plc2.get('address'):
        raise RuntimeError("writeSettings needs the PLC2 path: pass plc2Address (or plc2Gateway + plc2DeviceName), or set Path PLC2 in the editor, first. PLC2 device reads: %s" % plc2)
    owner_guid = _owning_device_guid(om, handle, red_guid)
    if owner_guid is None:
        raise RuntimeError("No PLC1 device above the redundancy object")
    online_mgr = SystemInstances.OnlineMgr
    for label, guid in (('PLC1', owner_guid), ('PLC2', device_guid)):
        dev = online_mgr.GetOnlineDevice(guid)
        if dev is None:
            raise RuntimeError("%s: no online device for guid %s" % (label, guid))
        was_connected = bool(dev.IsConnected)
        try:
            if not was_connected:
                dev.Connect()
            if not dev.IsConnected:
                raise RuntimeError("%s: not connected after Connect()" % label)
            print("DEBUG: %s reachable" % label)
        except Exception as e:
            raise RuntimeError("%s is not reachable, settings not written: %s" % (label, e))
        finally:
            if not was_connected:
                try:
                    dev.Disconnect()
                except Exception:
                    pass


def _plc2_path(om, handle, device_guid):
    info = {}
    try:
        dev = om.GetObjectToRead(handle, device_guid).Object
        cs = dev.CommunicationSettings
        try:
            info['address'] = str(cs.Address) if cs.Address is not None else ''
        except Exception:
            info['address'] = ''
        try:
            info['name'] = str(cs.Name)
        except Exception:
            pass
        try:
            info['gateway'] = str(cs.Gateway)
        except Exception:
            pass
    except Exception as e:
        info['error'] = str(e)
    return info


try:
    print("DEBUG: create_redundancy_config: Project='%s' parent='%s' name='%s'" % (PROJECT_FILE_PATH, PARENT_PATH, OBJECT_NAME))
    if 'register_device_credentials_if_set' in globals():
        register_device_credentials_if_set()
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)

    parent = find_object_by_path_robust(primary_project, PARENT_PATH, "application")
    if parent is None:
        raise ValueError("Application not found at path '%s'" % PARENT_PATH)

    import System
    for _asm_name in ('SystemInstances', 'Objects', 'ObjectsWin'):
        try:
            _load_assembly(_asm_name)
        except Exception as e:
            print("DEBUG: reference %s failed: %s" % (_asm_name, e))
    from _3S.CoDeSys.Core import SystemInstances
    handle = primary_project.handle
    om = SystemInstances.ObjectMgr

    existing = _find_redundancy_child(parent)
    created = False
    if existing is not None:
        red_guid = existing.guid
        print("DEBUG: redundancy object exists ('%s', guid %s) - updating" % (existing.get_name(), red_guid))
    else:
        factory = None
        for f in om.ObjectFactoryManager.Factories:
            try:
                if f.ObjectType is not None and f.ObjectType.FullName == REDUNDANCY_OBJECT_TYPE:
                    factory = f
                    break
            except Exception:
                continue
        if factory is None:
            raise RuntimeError("No Redundancy Configuration factory registered (is the CODESYS Redundancy add-on installed for this profile?)")
        new_obj = factory.Create()
        red_guid = System.Guid.NewGuid()
        om.AddObject(handle, parent.guid, red_guid, new_obj, OBJECT_NAME, -1)
        try:
            factory.ObjectCreated(handle, red_guid)
        except Exception as e:
            print("DEBUG: factory.ObjectCreated failed: %s" % e)
        created = True
        print("DEBUG: redundancy object created guid=%s" % red_guid)

    mo = om.GetObjectToModify(handle, red_guid)
    ro = mo.Object
    settings = ro.Settings
    for key, value in SETTINGS.items():
        if key not in SETTING_KINDS:
            raise ValueError("Unknown redundancy setting '%s'" % key)
        setattr(settings, key, _coerce(SETTING_KINDS[key], value))
    if ro.DeviceObjectGuid == System.Guid.Empty:
        ro.DeviceObjectGuid = System.Guid.NewGuid()
        print("DEBUG: assigned DeviceObjectGuid %s" % ro.DeviceObjectGuid)
    device_guid = ro.DeviceObjectGuid

    area_report = {'nonRedundant': [], 'redundant': []}
    for p in NON_REDUNDANT_PATHS:
        obj = find_object_by_path_robust(primary_project, p, "non-redundant object")
        if obj is None:
            raise ValueError("Object to exclude from synchronization not found: '%s'" % p)
        if not _has_non_redundant_area(ro, obj.guid):
            ro.RegisterNonRedundantArea(obj.guid)
        area_report['nonRedundant'].append(p)
    for p in REDUNDANT_PATHS:
        obj = find_object_by_path_robust(primary_project, p, "redundant object")
        if obj is None:
            raise ValueError("Object to include in synchronization not found: '%s'" % p)
        if _has_non_redundant_area(ro, obj.guid):
            ro.UnregisterNonRedundantArea(obj.guid)
        area_report['redundant'].append(p)
    # The hidden device is created BEFORE the object is committed: committing a
    # DeviceObjectGuid that points at nothing is exactly the state that makes
    # every later compile pop "The object GUID ... is not valid".
    hidden_created = _ensure_hidden_device(om, handle, red_guid, device_guid)
    om.SetObject(mo, True, None)
    print("DEBUG: redundancy object committed")

    path_set = False
    if PLC2_GATEWAY and (PLC2_DEVICE_NAME or PLC2_ADDRESS):
        before = _plc2_path(om, handle, device_guid)
        if PLC2_ADDRESS:
            _set_path_plc2_direct(handle, device_guid, PLC2_GATEWAY, PLC2_ADDRESS)
        else:
            _run_batch_command('_3S.CoDeSys.Redundancy.SetActivePathPlc2Command', [str(red_guid), PLC2_GATEWAY, PLC2_DEVICE_NAME])
        after = _plc2_path(om, handle, device_guid)
        # SetActivePath returns quietly without binding in several cases
        # (gateway not found, device not in the scan, cancelled safety popup),
        # so success is judged from the hidden device's communication settings.
        if not after.get('address'):
            raise RuntimeError("Set Path PLC2 did not bind a device: no address on the PLC2 device after gateway '%s' / '%s' (before: %s, after: %s)" % (PLC2_GATEWAY, PLC2_ADDRESS or PLC2_DEVICE_NAME, before, after))
        path_set = True

    try:
        primary_project.save()
        print("DEBUG: project saved")
    except Exception as e:
        print("WARN: project.save() raised %s" % e)

    write_command_ran = False
    if WRITE_SETTINGS:
        # WriteSettingsCommand reports connect/write failures in a modal message
        # box and does not raise, so both PLC paths must be usable first.
        _check_devices_reachable(om, handle, red_guid, device_guid)
        _run_batch_command('_3S.CoDeSys.Redundancy.WriteSettingsCommand', [str(red_guid)])
        write_command_ran = True

    check = om.GetObjectToRead(handle, red_guid).Object
    non_redundant = []
    try:
        for a in check.NonRedundantAreas:
            try:
                non_redundant.append(str(om.GetMetaObjectStub(handle, a.ObjectGuid).Name))
            except Exception:
                non_redundant.append(str(a))
    except Exception as e:
        non_redundant = ['unreadable: %s' % e]
    summary = {
        'object': str(om.GetMetaObjectStub(handle, red_guid).Name),
        'guid': str(red_guid),
        'created': created,
        'settings': _settings_dict(check.Settings),
        'nonRedundantAreas': non_redundant,
        'areasRequested': area_report,
        'plc2Device': {
            'guid': str(device_guid),
            'created': hidden_created,
            'exists': bool(om.ExistsObject(handle, device_guid)),
            'pathSetBy': ('address' if PLC2_ADDRESS else 'scan') if path_set else None,
            'path': _plc2_path(om, handle, device_guid),
        },
        # The Write command reports its own failures in a modal message box and
        # never raises, so this says the command ran, NOT that both controllers
        # took the settings. Confirm on the PLC (FW31: the [CmpRedundancy] /
        # [CmpRedundancyConnectionIP] sections of CODESYSControl.cfg).
        'writeCommandRan': write_command_ran,
        'writeVerified': False,
    }
    print("### REDUNDANCY_CONFIG_START ###")
    print(json.dumps(summary))
    print("### REDUNDANCY_CONFIG_END ###")
    print("SCRIPT_SUCCESS: Redundancy Configuration '%s' configured." % summary['object'])
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error configuring redundancy in project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
