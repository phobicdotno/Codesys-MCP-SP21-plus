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
        print("DEBUG: ScriptProject.handle unavailable (%s), trying APEnvironment.ProjectMgr" % e)
    pm = apenv.ProjectMgr
    proj = pm.PrimaryProject
    h = proj.Handle
    print("DEBUG: project handle via ProjectMgr.PrimaryProject.Handle = %s" % h)
    return h


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
    clr.AddReference('_3S.CoDeSys.Core')
    from _3S.CoDeSys.Core import APEnvironment
    handle = _project_handle(primary_project, APEnvironment)
    om = APEnvironment.ObjectMgr

    obj = om.GetObjectToModify(handle, gvl_guid)
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

    om.SetObject(handle, obj)
    print("DEBUG: SetObject committed")
    try:
        primary_project.save()
        print("DEBUG: project saved")
    except Exception as e:
        print("WARN: project.save() raised %s" % e)

    # read back through a fresh read handle
    check = om.GetObjectToRead(handle, gvl_guid)
    cnvp = check.NetVarProperties
    summary = {
        'gvl': GVL_PATH,
        'enabled': bool(getattr(cnvp, 'Enabled', False)),
        'protocol': str(getattr(cnvp, 'ProtocolName', '')),
        'list_identifier': str(getattr(cnvp, 'ListIdentifier', '')),
        'task': str(getattr(cnvp, 'TaskName', '')),
        'cyclic': bool(getattr(cnvp, 'TransmitCyclic', False)),
        'interval': str(getattr(cnvp, 'Interval', '')),
        'broadcast_param': used_addr or '',
        'port_param': used_port or '',
    }
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
