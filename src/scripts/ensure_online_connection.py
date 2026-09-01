import traceback

# --- Function to ensure an online connection to the active application ---
def ensure_online_connection(primary_project):
    """Get or create an online application connection for the active application."""
    print("DEBUG: Ensuring online connection...")
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)

    target_app = None
    app_name = "N/A"

    # Try getting active application
    try:
        target_app = primary_project.active_application
        if target_app:
            app_name = getattr(target_app, 'get_name', lambda: "Unnamed App")()
    except Exception as e:
        print("WARN: Could not get active application: %s" % e)

    # Search for first application if no active
    if not target_app:
        try:
            all_children = primary_project.get_children(True)
            for child in all_children:
                if hasattr(child, 'is_application') and child.is_application:
                    target_app = child
                    app_name = getattr(child, 'get_name', lambda: "Unnamed App")()
                    break
        except Exception as e:
            print("WARN: Error finding application: %s" % e)

    if not target_app:
        raise RuntimeError("No application found in project.")

    print("DEBUG: Using application: %s" % app_name)

    # Try to get or create online application
    online_app = None

    # Pattern 1: app.create_online_application()
    if hasattr(target_app, 'create_online_application'):
        try:
            online_app = target_app.create_online_application()
            if online_app:
                print("DEBUG: Created online application via app.create_online_application()")
                return online_app, target_app
        except Exception as e:
            print("DEBUG: app.create_online_application() failed: %s" % e)

    # Pattern 2: scriptengine online module
    try:
        import scriptengine as se
        if hasattr(se, 'online'):
            online_module = se.online
            if hasattr(online_module, 'create_online_application'):
                try:
                    online_app = online_module.create_online_application(target_app)
                    if online_app:
                        print("DEBUG: Created online application via scriptengine.online.create_online_application()")
                        return online_app, target_app
                except Exception as e:
                    print("DEBUG: scriptengine.online.create_online_application() failed: %s" % e)
    except Exception as e:
        print("DEBUG: scriptengine online module access failed: %s" % e)

    # Pattern 3: Check if there's already an online_application property
    if hasattr(target_app, 'online_application'):
        try:
            online_app = target_app.online_application
            if online_app:
                print("DEBUG: Found existing online application via app.online_application")
                return online_app, target_app
        except Exception as e:
            print("DEBUG: app.online_application failed: %s" % e)

    if not online_app:
        raise RuntimeError("Could not create online application connection. Ensure a device/gateway is configured in the project.")

    # Open the shared device session before returning. The IDE's
    # "right-click device -> Connect" maps to ScriptOnlineDevice.connect()
    # on a ScriptOnlineDevice created from the project's device object.
    # Without this, login() may pop dialogs the agent can't see or hang
    # while it waits for a session that nobody opened.
    _ensure_device_connected(primary_project, target_app)

    return online_app, target_app


def _ensure_device_connected(primary_project, target_app=None):
    """Locate the project's PLC device and open a shared online session
    on it if one isn't already open. Idempotent. Best-effort: any failure
    is logged but does NOT abort -- login() will surface its own error
    if the session truly couldn't be opened."""
    try:
        import scriptengine as _se
        online = getattr(_se, 'online', None)
        if online is None or not hasattr(online, 'create_online_device'):
            print("DEBUG: ensure_device_connected: scriptengine.online.create_online_device unavailable -- skipping")
            return

        # Inline device-pick (helper find_target_device may not be in scope
        # here -- ensure_online_connection.py is concatenated into scripts
        # that don't always import it). Keep selection criteria identical.
        target_device = None
        routed = []
        try:
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
                routed.append(c)
        except Exception as e:
            print("DEBUG: ensure_device_connected: device walk failed: %s" % e)
            return
        # Multi-device projects: prefer the routed device that hosts the
        # target application. Single-device projects keep the historical
        # 'first routed device' behaviour.
        if len(routed) > 1 and target_app is not None:
            try:
                node = target_app
                guard = 0
                while node is not None and guard < 32 and not hasattr(node, 'active_application'):
                    guard += 1
                    if getattr(node, 'is_device', False):
                        for d in routed:
                            try:
                                if str(d.guid) == str(node.guid):
                                    target_device = d
                            except Exception:
                                pass
                        break
                    node = node.parent
            except Exception as e:
                print("DEBUG: ensure_device_connected: app->device walk failed: %s" % e)
            if target_device is not None:
                print("DEBUG: ensure_device_connected: %d routed devices; using the one hosting the target application" % len(routed))
        if target_device is None and routed:
            target_device = routed[0]

        if target_device is None:
            print("DEBUG: ensure_device_connected: no PLC device with route -- skipping")
            return

        try:
            online_device = online.create_online_device(target_device)
        except Exception as e:
            print("DEBUG: ensure_device_connected: create_online_device failed: %s" % e)
            return

        # Already connected? Nothing to do.
        try:
            if getattr(online_device, 'connected', False) or getattr(online_device, 'shared_connected', False):
                print("DEBUG: ensure_device_connected: device session already open -- skipping connect()")
                return
        except Exception:
            pass

        try:
            online_device.connect()
            print("DEBUG: ensure_device_connected: online_device.connect() succeeded")
        except Exception as e:
            # Don't abort -- login() runs next and has its own retry
            # machinery for session-open errors. Just log so the failure
            # is visible in the script output.
            print("DEBUG: ensure_device_connected: online_device.connect() failed: %s: %s -- letting login() retry" % (type(e).__name__, e))
    except Exception as e:
        print("DEBUG: ensure_device_connected: unexpected error: %s: %s -- skipping" % (type(e).__name__, e))
# --- End of ensure_online_connection function ---


# --- Function to ensure the online application is logged in ---
def ensure_logged_in(online_app, login_wait_seconds=30):
    """Idempotently log into the device. In persistent mode the login state
    survives across calls and this is a no-op via online_app.is_logged_in.
    In headless mode each tool call spawns a fresh CODESYS process, so any
    online tool (start_stop, read_variable, write_variable,
    read_running_version_online) needs to log in itself before its action.

    Without this helper, tools other than connect_to_device + download_to_device
    fail in headless mode with 'Application not logged in.' (start/stop) or
    'Invalid expression' (read/write).

    Mirrors the SP-version-drift login probe in connect_to_device.py:
    OnlineChangeOption (older) vs LoginMode (SP21+) vs members on the
    online_app object itself; (mode, force_download_bool) two-arg shape vs
    (mode,) one-arg shape vs no-arg fallback. Prefers least-invasive
    'TryOnlineChange' / 'OnlineChangeOnly' semantics."""
    import scriptengine as _se  # local import; ensure_online_connection.py
                                # is concatenated into the script body so
                                # the top-level import in the main script
                                # is also visible, but keep this defensive.
    # Short-circuit: already logged in (persistent mode).
    if hasattr(online_app, 'is_logged_in'):
        try:
            if online_app.is_logged_in:
                print("DEBUG: ensure_logged_in: already logged in (persistent session).")
                return
        except Exception as e:
            print("DEBUG: ensure_logged_in: is_logged_in property raised: %s" % e)

    if not hasattr(online_app, 'login'):
        raise TypeError("Online application does not support login().")

    # Build enum candidate list -- same logic as connect_to_device.py's
    # main body, kept here so headless tool calls don't have to
    # re-implement it. Probe both script_engine.* and online_app.* for
    # LoginMode / OnlineChangeOption.
    enum_sources = []
    for src_name in ('LoginMode', 'OnlineChangeOption'):
        if hasattr(_se, src_name):
            try:
                enum_sources.append((src_name, getattr(_se, src_name)))
            except Exception:
                pass
    for src_name in ('LoginMode', 'OnlineChangeOption'):
        if hasattr(online_app, src_name):
            try:
                enum_sources.append(('online_app.' + src_name, getattr(online_app, src_name)))
            except Exception:
                pass

    preferred_order = ('TryOnlineChange', 'OnlineChangeOnly', 'Try', 'OnlineChange',
                       'WithDownload', 'ForceDownload', 'Download',
                       'None_', 'None')
    enum_candidates = []
    seen_keys = set()
    for src_name, oc in enum_sources:
        try:
            members = sorted([m for m in dir(oc) if not m.startswith('_')])
        except Exception:
            members = []
        for preferred in preferred_order:
            if preferred in members:
                key = '%s.%s' % (src_name, preferred)
                if key not in seen_keys:
                    try:
                        enum_candidates.append((key, getattr(oc, preferred)))
                        seen_keys.add(key)
                    except Exception:
                        pass
        for m in members:
            key = '%s.%s' % (src_name, m)
            if key not in seen_keys:
                try:
                    enum_candidates.append((key, getattr(oc, m)))
                    seen_keys.add(key)
                except Exception:
                    pass

    call_shapes = []
    for nm, val in enum_candidates:
        call_shapes.append(("login(%s, False)" % nm, (val, False)))
        call_shapes.append(("login(%s, True)" % nm, (val, True)))
        call_shapes.append(("login(%s)" % nm, (val,)))
    call_shapes.append(("login(False)", (False,)))
    call_shapes.append(("login(True)", (True,)))
    call_shapes.append(("login()", ()))

    last_err = None
    logged_in = False
    for desc, args in call_shapes:
        try:
            online_app.login(*args)
            print("DEBUG: ensure_logged_in: %s succeeded" % desc)
            logged_in = True
            break
        except Exception as e:
            last_err = e

    if not logged_in:
        raise RuntimeError("ensure_logged_in: all login() call shapes failed. Last error: %s" % last_err)

    # Settle wait. Same STABLE_STATES as connect_to_device.
    STABLE_STATES = ('run', 'stop', 'connected', 'halt', 'breakpoint')
    state = "unknown"
    for elapsed in range(login_wait_seconds):
        if hasattr(online_app, 'application_state'):
            try:
                state = str(online_app.application_state)
            except Exception:
                pass
        if state.lower() in STABLE_STATES:
            print("DEBUG: ensure_logged_in: state stabilised at '%s' after %ds" % (state, elapsed))
            return
        try:
            _se.system.delay(1000)
        except Exception:
            pass
    print("DEBUG: ensure_logged_in: state did not stabilise within %ds (last='%s'); proceeding anyway." % (login_wait_seconds, state))
# --- End of ensure_logged_in function ---
