import sys, scriptengine as script_engine, os, traceback, json

# set_nvl_sender: turn a GVL into a Network Variable List SENDER (or update
# its network properties). The scripting API has no NVL support; this uses
# the Automation Platform API that the IDE's own dialog uses, reflected from
# the SP21 Patch 5 assemblies:
#   GVLObject.dll  IGVLObject2.CreateNetVarProperties() -> INetVarProperties
#                  INetVarProperties: ProtocolName, TaskName, ListIdentifier,
#                    TransmitCyclic, Interval, TransmitOnChange, MinimumGap,
#                    TransmitOnEvent, EventVariable, PackVariables, Checksum,
#                    Acknowledge, GetParameterValue(name, out value)
#                  INetVarProperties2.CreateGuids()
#                  INetVarProperties4.SetParameterValue(name, value)
# Object access goes through APEnvironment.ObjectMgr (GetObjectToModify /
# SetObject). Every uncertain call is probed and reported so a failure
# explains itself.

GVL_PATH = {GVL_PATH}
LIST_IDENTIFIER = {LIST_IDENTIFIER}
TASK_NAME = {TASK_NAME}
PORT = {PORT}
BROADCAST_ADDRESS = {BROADCAST_ADDRESS}
INTERVAL = {INTERVAL}
MIN_GAP = {MIN_GAP}
CYCLIC = {CYCLIC}
ON_CHANGE = {ON_CHANGE}
PACK_VARIABLES = {PACK_VARIABLES}
CHECKSUM = {CHECKSUM}
ACKNOWLEDGE = {ACKNOWLEDGE}


def _names(obj, needle=''):
    try:
        return sorted([n for n in dir(obj) if needle.lower() in n.lower() and not n.startswith('__')])
    except Exception:
        return []


def _project_handle(primary_project, apenv):
    try:
        h = primary_project.handle
        print("DEBUG: project handle via ScriptProject.handle = %s" % h)
        return h
    except Exception as e:
        print("DEBUG: ScriptProject.handle unavailable (%s); engine members: %s" % (e, ', '.join(sorted(n for n in dir(apenv) if not n.startswith('_')))))
        raise RuntimeError("No project handle available (ScriptProject.handle missing on this SP)")


def _set_param(nvp, name, value):
    """Try INetVarProperties4.SetParameterValue with several spellings of a
    protocol parameter name. Returns the name that worked or None."""
    for candidate in name:
        try:
            nvp.SetParameterValue(candidate, str(value))
            ok, current = True, None
            try:
                res = nvp.GetParameterValue(candidate, None)
                # IronPython returns (bool, outvalue) for out parameters
                if isinstance(res, tuple):
                    ok, current = res[0], res[1]
                else:
                    ok = bool(res)
            except Exception:
                pass
            if ok:
                print("DEBUG: parameter '%s' := '%s' (read back: %s)" % (candidate, value, current))
                return candidate
        except Exception as e:
            print("DEBUG: SetParameterValue('%s') failed: %s" % (candidate, e))
    return None


try:
    print("DEBUG: set_nvl_sender: Project='%s' GVL='%s' list=%s task='%s'" % (PROJECT_FILE_PATH, GVL_PATH, LIST_IDENTIFIER, TASK_NAME))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)

    gvl = find_object_by_path_robust(primary_project, GVL_PATH, "GVL")
    if gvl is None:
        raise ValueError("GVL not found at path '%s'" % GVL_PATH)
    gvl_guid = gvl.guid
    print("DEBUG: GVL '%s' guid=%s" % (gvl.get_name(), gvl_guid))

    import clr
    import System
    for _name in ('SystemInstances', 'Objects', 'ObjectsWin'):
        _found = None
        for _asm in System.AppDomain.CurrentDomain.GetAssemblies():
            if _asm.GetName().Name == _name:
                _found = _asm
                break
        clr.AddReference(_found if _found is not None else _name)
    from _3S.CoDeSys.Core import SystemInstances
    handle = _project_handle(primary_project, SystemInstances)
    om = SystemInstances.ObjectMgr

    mo = om.GetObjectToModify(handle, gvl_guid)
    obj = mo.Object
    print("DEBUG: IObject type: %s" % obj.GetType().FullName)

    nvp = None
    try:
        nvp = obj.NetVarProperties
    except Exception as e:
        print("DEBUG: obj.NetVarProperties read failed: %s" % e)
    if nvp is None:
        if not hasattr(obj, 'CreateNetVarProperties'):
            raise RuntimeError("Object has no CreateNetVarProperties (not an IGVLObject2?). Members: %s" % ', '.join(_names(obj, 'net')))
        nvp = obj.CreateNetVarProperties()
        print("DEBUG: created NetVarProperties")
    else:
        print("DEBUG: existing NetVarProperties (Enabled=%s, list=%s)" % (getattr(nvp, 'Enabled', '?'), getattr(nvp, 'ListIdentifier', '?')))

    nvp.ProtocolName = "UDP"
    nvp.TaskName = TASK_NAME
    nvp.ListIdentifier = str(LIST_IDENTIFIER)
    nvp.TransmitCyclic = CYCLIC
    nvp.Interval = INTERVAL
    nvp.TransmitOnChange = ON_CHANGE
    nvp.MinimumGap = MIN_GAP
    nvp.TransmitOnEvent = False
    nvp.PackVariables = PACK_VARIABLES
    nvp.Checksum = CHECKSUM
    nvp.Acknowledge = ACKNOWLEDGE

    used_addr = _set_param(nvp, ["Broadcast Adr.", "Broadcast address", "BroadcastAddress", "Broadcast Adr", "Broadcast"], BROADCAST_ADDRESS)
    used_port = _set_param(nvp, ["Port", "UDP Port", "Portnumber"], PORT)
    if used_addr is None or used_port is None:
        print("WARN: could not set %s%s - NetVarProperties members: %s" % (
            '' if used_addr else 'broadcast address ', '' if used_port else 'port', ', '.join(_names(nvp))))

    try:
        if hasattr(nvp, 'CreateGuids'):
            nvp.CreateGuids()
            print("DEBUG: CreateGuids() done (task slots %s / %s)" % (getattr(nvp, 'guidTaskStartSlot', '?'), getattr(nvp, 'guidTaskEndSlot', '?')))
    except Exception as e:
        print("DEBUG: CreateGuids failed: %s" % e)

    # CreateNetVarProperties returns a DETACHED properties object on SP21 P5;
    # attach it through the concrete class's writable member (found by
    # reflection: the interface property is get-only).
    try:
        if obj.NetVarProperties is None:
            from System.Reflection import BindingFlags
            _t = obj.GetType()
            _flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance
            _attached_via = None
            for _pname in ('NetvarSettings', 'NetVarProperties'):
                _pi = _t.GetProperty(_pname, _flags)
                if _pi is not None and _pi.CanWrite:
                    _pi.SetValue(obj, nvp, None)
                    _attached_via = 'property ' + _pname
                    break
            if _attached_via is None:
                for _fi in _t.GetFields(_flags):
                    if 'netvar' in _fi.Name.lower():
                        _fi.SetValue(obj, nvp)
                        _attached_via = 'field ' + _fi.Name
                        break
            print("DEBUG: attach via %s" % _attached_via)
    except Exception as e:
        print("DEBUG: reflective attach failed: %s" % e)
    try:
        attached = obj.NetVarProperties
        print("DEBUG: pre-commit NetVarProperties attached: %s (same as nvp: %s)" % (attached is not None, attached is nvp))
    except Exception as e:
        print("DEBUG: pre-commit NetVarProperties read failed: %s" % e)
    om.SetObject(mo, True, None)
    print("DEBUG: SetObject committed")
    mid = om.GetObjectToRead(handle, gvl_guid).Object
    mid_nvp = None
    try:
        mid_nvp = mid.NetVarProperties
    except Exception as e:
        print("DEBUG: post-commit read failed: %s" % e)
    print("DEBUG: post-commit NetVarProperties present: %s" % (mid_nvp is not None))
    if mid_nvp is None:
        ifaces = ', '.join(sorted(i.Name for i in obj.GetType().GetInterfaces() if 'GVL' in i.Name or 'NetVar' in i.Name))
        print("DEBUG: obj interfaces: %s" % ifaces)
        print("DEBUG: obj members with netvar: %s" % ', '.join(_names(obj, 'netvar')))
    try:
        primary_project.save()
        print("DEBUG: project saved")
    except Exception as e:
        print("WARN: project.save() raised %s" % e)

    # read back through a fresh read handle
    check = om.GetObjectToRead(handle, gvl_guid).Object
    cnvp = check.NetVarProperties
    summary = {
        'gvl': GVL_PATH,
        'persisted': cnvp is not None,
        'enabled': bool(getattr(cnvp, 'Enabled', False)),
        'protocol': str(getattr(cnvp, 'ProtocolName', '')),
        'list_identifier': str(getattr(cnvp, 'ListIdentifier', '')),
        'task': str(getattr(cnvp, 'TaskName', '')),
        'cyclic': bool(getattr(cnvp, 'TransmitCyclic', False)),
        'interval': str(getattr(cnvp, 'Interval', '')),
        'broadcast_param': used_addr or '',
        'port_param': used_port or '',
    }
    if cnvp is None:
        raise RuntimeError("NetVarProperties did not persist (still None after commit) - see DEBUG lines above")
    print("### NVL_SENDER_START ###")
    print(json.dumps(summary))
    print("### NVL_SENDER_END ###")
    print("SCRIPT_SUCCESS: NVL sender configured on %s (list %s)." % (GVL_PATH, LIST_IDENTIFIER))
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error configuring NVL sender in project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
