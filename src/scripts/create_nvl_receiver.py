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
        print("DEBUG: ScriptProject.handle unavailable (%s), trying APEnvironment.ProjectMgr" % e)
    h = apenv.ProjectMgr.PrimaryProject.Handle
    print("DEBUG: project handle via ProjectMgr.PrimaryProject.Handle = %s" % h)
    return h


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
    clr.AddReference('_3S.CoDeSys.Core')
    from _3S.CoDeSys.Core import APEnvironment
    handle = _project_handle(primary_project, APEnvironment)
    om = APEnvironment.ObjectMgr

    existing = _find_existing(parent, RECEIVER_NAME)
    created = False
    if existing is not None:
        print("DEBUG: receiver '%s' already exists (guid %s) - updating" % (RECEIVER_NAME, existing.guid))
        obj_guid = existing.guid
    else:
        obj = None
        errors = []
        for type_guid in NVL_TYPE_GUIDS:
            g = System.Guid(type_guid)
            for desc, fn in [
                ("CreateObject(typeGuid)", lambda: om.CreateObject(g)),
                ("CreateObject(typeGuid, name)", lambda: om.CreateObject(g, RECEIVER_NAME)),
                ("GetObjectFactory(typeGuid).Create()", lambda: om.GetObjectFactory(g).Create()),
                ("GetObjectFactory(typeGuid).Create(name)", lambda: om.GetObjectFactory(g).Create(RECEIVER_NAME)),
            ]:
                try:
                    obj = fn()
                    if obj is not None:
                        print("DEBUG: created NVL object via %s with type %s" % (desc, type_guid))
                        break
                except Exception as e:
                    errors.append("%s [%s]: %s" % (desc, type_guid, e))
            if obj is not None:
                break
        if obj is None:
            raise RuntimeError("Could not create the NVL receiver object. Tried: %s. ObjectMgr members: %s" % (
                ' | '.join(errors), ', '.join(_names(om))))
        # name + add under the parent
        try:
            obj.MetaObject.Name = RECEIVER_NAME
        except Exception as e:
            print("DEBUG: setting MetaObject.Name failed: %s" % e)
        added = False
        add_errors = []
        for desc, fn in [
            ("AddObject(handle, parentGuid, obj, -1)", lambda: om.AddObject(handle, parent.guid, obj, -1)),
            ("AddObject(handle, parentGuid, obj)", lambda: om.AddObject(handle, parent.guid, obj)),
            ("AddObject(handle, parentGuid, name, obj, -1)", lambda: om.AddObject(handle, parent.guid, RECEIVER_NAME, obj, -1)),
        ]:
            try:
                fn()
                added = True
                print("DEBUG: added via %s" % desc)
                break
            except Exception as e:
                add_errors.append("%s: %s" % (desc, e))
        if not added:
            raise RuntimeError("Could not add the NVL receiver under '%s'. Tried: %s. ObjectMgr members: %s" % (
                PARENT_PATH, ' | '.join(add_errors), ', '.join(_names(om, 'add'))))
        created = True
        new_obj = _find_existing(parent, RECEIVER_NAME)
        if new_obj is None:
            raise RuntimeError("Receiver added but not found under parent afterwards")
        obj_guid = new_obj.guid

    recv = om.GetObjectToModify(handle, obj_guid)
    print("DEBUG: receiver IObject type: %s" % recv.GetType().FullName)
    recv.SenderGVLGuid = sender_guid
    recv.TaskName = TASK_NAME
    nvp = None
    try:
        nvp = recv.NetVarProperties
    except Exception as e:
        print("DEBUG: receiver NetVarProperties read failed: %s" % e)
    if nvp is not None:
        try:
            nvp.ProtocolName = "UDP"
            nvp.ListIdentifier = str(LIST_IDENTIFIER)
            nvp.TaskName = TASK_NAME
            for candidate in ["Broadcast Adr.", "Broadcast address", "BroadcastAddress"]:
                try:
                    nvp.SetParameterValue(candidate, BROADCAST_ADDRESS)
                    break
                except Exception:
                    pass
            for candidate in ["Port", "UDP Port"]:
                try:
                    nvp.SetParameterValue(candidate, str(PORT))
                    break
                except Exception:
                    pass
        except Exception as e:
            print("DEBUG: setting receiver NetVarProperties failed: %s" % e)
    try:
        if hasattr(recv, 'CreateGuids'):
            recv.CreateGuids()
    except Exception as e:
        print("DEBUG: CreateGuids failed: %s" % e)
    om.SetObject(handle, recv)
    print("DEBUG: SetObject committed")
    try:
        primary_project.save()
        print("DEBUG: project saved")
    except Exception as e:
        print("WARN: project.save() raised %s" % e)

    check = om.GetObjectToRead(handle, obj_guid)
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
