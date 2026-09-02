import sys, scriptengine as script_engine, os, traceback, json

# create_nvl_receiver: add a "Network Variable List (Receiver)" object under an
# application and bind it to a sender GVL (INVLObject.SenderGVLGuid), using
# the Automation Platform API (NVLObject.dll INVLObject: SenderGVLGuid,
# TaskName, NetVarProperties; INVLObject2.CreateGuids()). Object creation
# goes through APEnvironment.ObjectMgr; because the exact factory call is not
# documented, several candidates are tried and every failure is reported
# with the manager's member list so the first run explains the API.

RECEIVER_NAME = {RECEIVER_NAME}
PARENT_PATH = {PARENT_PATH}
SENDER_GVL_PATH = {SENDER_GVL_PATH}
TASK_NAME = {TASK_NAME}
LIST_IDENTIFIER = {LIST_IDENTIFIER}
PORT = {PORT}
BROADCAST_ADDRESS = {BROADCAST_ADDRESS}

# Object type GUID candidates found in NVLObject.plugin.dll (SP21 P5).
NVL_TYPE_GUIDS = ["9F8DD862-5ACD-45e3-BC9E-44A56F3A2C2B", "E5B60C93-5445-4e40-ADA9-CD9C005549B4"]


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


def _find_existing(parent, name):
    try:
        for c in parent.get_children(False):
            try:
                if c.get_name() == name:
                    return c
            except Exception:
                pass
    except Exception:
        pass
    return None


try:
    print("DEBUG: create_nvl_receiver: Project='%s' name='%s' parent='%s' sender='%s'" % (PROJECT_FILE_PATH, RECEIVER_NAME, PARENT_PATH, SENDER_GVL_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)

    parent = find_object_by_path_robust(primary_project, PARENT_PATH, "parent")
    if parent is None:
        raise ValueError("Parent not found at path '%s'" % PARENT_PATH)
    sender = find_object_by_path_robust(primary_project, SENDER_GVL_PATH, "sender GVL")
    if sender is None:
        raise ValueError("Sender GVL not found at path '%s'" % SENDER_GVL_PATH)
    sender_guid = sender.guid
    print("DEBUG: parent guid=%s sender guid=%s" % (parent.guid, sender_guid))

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

    existing = _find_existing(parent, RECEIVER_NAME)
    created = False
    if existing is not None:
        print("DEBUG: receiver '%s' already exists (guid %s) - updating" % (RECEIVER_NAME, existing.guid))
        obj_guid = existing.guid
    else:
        fm = om.ObjectFactoryManager
        factory = None
        names = []
        for f in fm.Factories:
            try:
                nm = str(f.Name)
                tn = f.ObjectType.FullName if f.ObjectType is not None else ''
            except Exception:
                continue
            names.append(nm)
            if 'NVLObject' in tn or 'Network Variable List' in nm:
                factory = f
                print("DEBUG: using factory '%s' (%s)" % (nm, tn))
                break
        if factory is None:
            raise RuntimeError("No NVL receiver factory found. Factories: %s" % ', '.join(sorted(set(names))))
        new_iobj = None
        try:
            new_iobj = factory.Create()
            print("DEBUG: factory.Create() ok: %s" % (new_iobj is not None))
        except Exception as e:
            print("DEBUG: factory.Create() failed: %s" % e)
        if new_iobj is None:
            t_obj = factory.ObjectType
            new_iobj = System.Activator.CreateInstance(t_obj)
            print("DEBUG: Activator.CreateInstance(%s) ok" % t_obj.FullName)
        new_guid = System.Guid.NewGuid()
        print("DEBUG: adding object guid=%s under parent=%s" % (new_guid, parent.guid))
        om.AddObject(handle, parent.guid, new_guid, new_iobj, RECEIVER_NAME, -1)
        print("DEBUG: AddObject ok")
        try:
            factory.ObjectCreated(handle, new_guid)
        except Exception as e:
            print("DEBUG: factory.ObjectCreated failed: %s" % e)
        created = True
        obj_guid = new_guid
        print("DEBUG: receiver created guid=%s" % obj_guid)

    mo = om.GetObjectToModify(handle, obj_guid)
    recv = mo.Object
    print("DEBUG: receiver IObject type: %s" % recv.GetType().FullName)
    recv.SenderGVLGuid = sender_guid
    recv.TaskName = TASK_NAME
    nvp = None
    try:
        nvp = recv.NetVarProperties
    except Exception as e:
        print("DEBUG: receiver NetVarProperties read failed: %s" % e)
    # A receiver MIRRORS its sender's network properties through SenderGVLGuid.
    # Giving the receiver's own properties a protocol/task would register a
    # second netvar manager on the same task and collide with the sender's
    # generated instance (Ambiguous use of NetVarManager_<proto>_<task>_0).
    if nvp is not None:
        try:
            if str(getattr(nvp, 'ProtocolName', '')):
                nvp.ProtocolName = ""
                print("DEBUG: cleared receiver's own ProtocolName (mirrors the sender)")
        except Exception as e:
            print("DEBUG: clearing receiver NetVarProperties failed: %s" % e)
    try:
        if hasattr(recv, 'CreateGuids'):
            recv.CreateGuids()
    except Exception as e:
        print("DEBUG: CreateGuids failed: %s" % e)
    om.SetObject(mo, True, None)
    print("DEBUG: SetObject committed")
    try:
        primary_project.save()
        print("DEBUG: project saved")
    except Exception as e:
        print("WARN: project.save() raised %s" % e)

    check = om.GetObjectToRead(handle, obj_guid).Object
    summary = {
        'receiver': RECEIVER_NAME,
        'parent': PARENT_PATH,
        'created': created,
        'sender_guid': str(getattr(check, 'SenderGVLGuid', '')),
        'sender_name': str(getattr(check, 'SenderGVLName', '')),
        'task': str(getattr(check, 'TaskName', '')),
    }
    print("### NVL_RECEIVER_START ###")
    print(json.dumps(summary))
    print("### NVL_RECEIVER_END ###")
    print("SCRIPT_SUCCESS: NVL receiver '%s' bound to sender '%s'." % (RECEIVER_NAME, SENDER_GVL_PATH))
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error creating NVL receiver in project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
