import sys, scriptengine as script_engine, os, traceback

LOGIN_WAIT_SECONDS = {LOGIN_WAIT_SECONDS}

try:
    print("DEBUG: connect_to_device script: Project='%s', LoginWaitSec=%d" % (
        PROJECT_FILE_PATH, LOGIN_WAIT_SECONDS))
    register_device_credentials_if_set()
    primary_project = ensure_project_open(PROJECT_FILE_PATH)

    online_app, target_app = ensure_online_connection(primary_project)
    app_name = getattr(target_app, 'get_name', lambda: "Unknown")()

    # Login to the device. The login() signature shifted across SPs:
    #   - Older: login() with no args, or login(OnlineChangeOption.TryOnlineChange)
    #   - SP21+/SP22: login(OnlineChangeOption, bool) -- two required positional
    #     args, with several enum members renamed (TryOnlineChange removed).
    # Probe what's available, then try a sequence of plausible call shapes.
    print("DEBUG: Calling login() on online application...")
    if not hasattr(online_app, 'login'):
        raise TypeError("Online application does not support login().")

    # Discover login-mode enum members defensively. Different SPs expose the
    # enum under different names and different module locations:
    #   - Pre-SP21: script_engine.OnlineChangeOption (TryOnlineChange / WithDownload / ...)
    #   - SP21+:    script_engine.LoginMode (rebadged; some members renamed/removed)
    #   - Some builds attach it to the online_app object instead.
    # Probe every known location and merge the discovered members.
    enum_sources = []
    for src_name in ('LoginMode', 'OnlineChangeOption'):
        if hasattr(script_engine, src_name):
            try:
                enum_sources.append((src_name, getattr(script_engine, src_name)))
            except Exception:
                pass
    for src_name in ('LoginMode', 'OnlineChangeOption'):
        if hasattr(online_app, src_name):
            try:
                enum_sources.append(('online_app.' + src_name, getattr(online_app, src_name)))
            except Exception:
                pass
    if not enum_sources:
        print("DEBUG: No login-mode enum found on script_engine or online_app -- relying on plain-bool fallbacks.")

    # Priority order: prefer "no-download / online change" semantics (least
    # invasive), then download variants, then null/none.
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
        print("DEBUG: %s members: %s" % (src_name, members))
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

    # Build call-shape candidates for login(): a list of (description, args-tuple).
    call_shapes = []
    for nm, val in enum_candidates:
        # Two-arg shape (most common SP21+): (mode, force_download_bool).
        call_shapes.append(("login(%s, False)" % nm, (val, False)))
        call_shapes.append(("login(%s, True)" % nm, (val, True)))
        # One-arg shape (older).
        call_shapes.append(("login(%s)" % nm, (val,)))
    # Three-arg shape some builds use: (mode, secondary-mode, bool). Try with
    # the strongest "do nothing" pair we can find at the front of candidates.
    if enum_candidates:
        first_nm, first_val = enum_candidates[0]
        call_shapes.append(("login(%s, %s, False)" % (first_nm, first_nm), (first_val, first_val, False)))
    # Also try plain bools and no-arg as fall-backs (for very old SPs).
    call_shapes.append(("login(False)", (False,)))
    call_shapes.append(("login(True)", (True,)))
    call_shapes.append(("login()", ()))

    last_err = None
    logged_in = False
    for desc, args in call_shapes:
        try:
            online_app.login(*args)
            print("DEBUG: %s succeeded" % desc)
            logged_in = True
            break
        except Exception as e:
            last_err = e
            # Print only the short error to keep log readable
            print("DEBUG: %s failed: %s: %s" % (desc, type(e).__name__, e))

    if not logged_in:
        raise RuntimeError("All login() call shapes failed. Last error: %s" % last_err)
    print("DEBUG: login() returned. Waiting up to %d seconds for state to stabilise" % LOGIN_WAIT_SECONDS)

    # Poll application_state. login() may return before the application
    # state has settled. Pump the message loop via system.delay() and exit
    # early once the state lands on a recognisable terminal value. With
    # deviceUser/devicePassword injected (register_device_credentials_if_set)
    # no login dialog appears; without them CODESYS falls back to its dialog.
    STABLE_STATES = ('run', 'stop', 'connected', 'halt', 'breakpoint')
    state = "unknown"
    for elapsed in range(LOGIN_WAIT_SECONDS):
        if hasattr(online_app, 'application_state'):
            try:
                state = str(online_app.application_state)
            except Exception:
                pass
        if state.lower() in STABLE_STATES:
            print("DEBUG: state stabilised at '%s' after %ds" % (state, elapsed))
            break
        try:
            script_engine.system.delay(1000)
        except Exception:
            pass

    print("Connected to device for application: %s" % app_name)
    print("Application State: %s" % state)
    print("SCRIPT_SUCCESS: Connected to device successfully.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error connecting to device for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
