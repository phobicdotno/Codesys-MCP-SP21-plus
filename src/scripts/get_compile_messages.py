import sys, scriptengine as script_engine, os, traceback, json


# ============================================================================
# Inlined helpers (shared with compile_project.py).
# Inlined rather than imported because the IPC executor concatenates helper
# scripts at runtime; siblings in src/scripts/ don't have a sys.path entry.
# Keep these two copies in sync.
# ============================================================================

_JSON_INT64_MAX = 9223372036854775807  # 2**63 - 1


def _coerce_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):
        return None


def _coerce_str(v):
    if v is None:
        return None
    try:
        return str(v)
    except Exception:
        return None


def _coerce_for_json(obj):
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, long)):  # noqa: F821 -- IronPython 2.7
        try:
            if obj > _JSON_INT64_MAX or obj < -_JSON_INT64_MAX - 1:
                return str(obj)
            return int(obj)
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            try:
                key = k if isinstance(k, str) else str(k)
            except Exception:
                continue
            out[key] = _coerce_for_json(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_coerce_for_json(v) for v in obj]
    return obj


def _build_message_entry(msg, category_name=None):
    entry = {}
    if hasattr(msg, 'severity'):
        try:
            sev = str(msg.severity).lower()
        except Exception:
            sev = 'unknown'
        if 'error' in sev:
            entry['severity'] = 'error'
        elif 'warning' in sev:
            entry['severity'] = 'warning'
        elif 'info' in sev:
            entry['severity'] = 'info'
        else:
            entry['severity'] = sev
    else:
        entry['severity'] = 'unknown'
    text = None
    for attr in ('text', 'message'):
        if hasattr(msg, attr):
            text = _coerce_str(getattr(msg, attr))
            if text is not None:
                break
    if text is None:
        text = _coerce_str(msg)
    entry['text'] = text
    if hasattr(msg, 'object_name'):
        entry['object'] = _coerce_str(msg.object_name)
    elif hasattr(msg, 'source'):
        entry['object'] = _coerce_str(msg.source)
    if hasattr(msg, 'line_number'):
        entry['line'] = _coerce_int(msg.line_number)
    elif hasattr(msg, 'position'):
        entry['line'] = _coerce_int(msg.position)
    cat = None
    for attr in ('category', 'category_name', 'category_guid'):
        if hasattr(msg, attr):
            try:
                v = getattr(msg, attr)
                if v is not None:
                    cat = _coerce_str(v)
                    if cat:
                        break
            except Exception:
                pass
    if not cat and category_name:
        cat = category_name
    if cat:
        entry['category'] = cat
    return entry


def _enumerate_categories(script_engine_arg):
    """Returns a list of (label, category_guid_or_None) tuples for every
    message category the IDE exposes plus a (None, None) sentinel for the
    no-filter call.

    Discovery path: script_engine.system.get_message_categories() (the
    METHOD) returns the live List[Guid]. script_engine.system.get_message_category_description(guid)
    gives the human-readable label per category. See compile_project.py
    for the verified-on-SP22 history note."""
    cats = [('<default-no-filter>', None)]
    se_sys = getattr(script_engine_arg, 'system', None)
    if se_sys is None or not hasattr(se_sys, 'get_message_categories'):
        return cats
    try:
        guids = se_sys.get_message_categories()
    except Exception as e:
        print("DEBUG: get_message_categories() raised: %s" % e)
        return cats
    if guids is None:
        return cats
    for g in guids:
        label = None
        try:
            if hasattr(se_sys, 'get_message_category_description'):
                label = _coerce_str(se_sys.get_message_category_description(g))
        except Exception:
            label = None
        if not label:
            label = _coerce_str(g) or '<unnamed>'
        cats.append((label, g))
    return cats


def _extract_all_messages(target_app, script_engine_arg):
    """Aggregate compile/build/library messages across every category we
    can probe. Returns a list of message-entry dicts, deduped by
    (severity, text, object, line)."""
    all_entries = []
    seen = set()

    def _add(entry):
        key = (
            entry.get('severity'),
            entry.get('text'),
            entry.get('object'),
            entry.get('line'),
        )
        if key in seen:
            return False
        seen.add(key)
        all_entries.append(entry)
        return True

    if target_app is not None and hasattr(target_app, 'get_message_objects'):
        for label, cat in _enumerate_categories(script_engine_arg):
            try:
                if cat is None:
                    msgs = target_app.get_message_objects()
                else:
                    try:
                        msgs = target_app.get_message_objects(cat)
                    except TypeError:
                        continue
            except Exception as e:
                print("DEBUG: app.get_message_objects(%s) failed: %s" % (label, e))
                continue
            if not msgs:
                continue
            count_before = len(all_entries)
            try:
                for m in msgs:
                    try:
                        _add(_build_message_entry(m, label))
                    except Exception as e:
                        print("DEBUG: failed to entry-ize msg from cat=%s: %s" % (label, e))
            except Exception:
                pass
            added = len(all_entries) - count_before
            if added > 0:
                print("DEBUG: app.get_message_objects(%s) added %d new" % (label, added))

    se_sys = getattr(script_engine_arg, 'system', None)
    if se_sys is not None and hasattr(se_sys, 'get_message_objects'):
        for label, cat in _enumerate_categories(script_engine_arg):
            try:
                if cat is None:
                    msgs = se_sys.get_message_objects()
                else:
                    try:
                        msgs = se_sys.get_message_objects(cat)
                    except TypeError:
                        continue
            except Exception as e:
                print("DEBUG: system.get_message_objects(%s) failed: %s" % (label, e))
                continue
            if not msgs:
                continue
            count_before = len(all_entries)
            try:
                for m in msgs:
                    try:
                        _add(_build_message_entry(m, label))
                    except Exception:
                        pass
            except Exception:
                pass
            added = len(all_entries) - count_before
            if added > 0:
                print("DEBUG: system.get_message_objects(%s) added %d new" % (label, added))

    if se_sys is not None and hasattr(se_sys, 'get_messages'):
        try:
            msgs = se_sys.get_messages()
            if msgs:
                count_before = len(all_entries)
                for m in msgs:
                    try:
                        _add(_build_message_entry(m, '<legacy>'))
                    except Exception:
                        pass
                added = len(all_entries) - count_before
                if added > 0:
                    print("DEBUG: system.get_messages() added %d new" % added)
        except Exception as e:
            print("DEBUG: system.get_messages() failed: %s" % e)

    return all_entries


def _count_severity(entries):
    e = w = i = o = 0
    for entry in entries:
        sev = entry.get('severity', 'unknown')
        if sev == 'error':
            e += 1
        elif sev == 'warning':
            w += 1
        elif sev == 'info':
            i += 1
        else:
            o += 1
    return e, w, i, o


def _render_messages_block(entries):
    try:
        messages_json = json.dumps(_coerce_for_json(entries))
    except TypeError as je:
        print("WARN: json.dumps raised %s -- retrying with default=str fallback" % je)
        messages_json = json.dumps(_coerce_for_json(entries), default=lambda o: str(o))
    e, w, i, o = _count_severity(entries)
    return messages_json, e, w, i, o


# ============================================================================
# Main
# ============================================================================

try:
    print("DEBUG: get_compile_messages script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)
    project_name = os.path.basename(PROJECT_FILE_PATH)
    target_app = None
    app_name = "N/A"

    try:
        target_app = primary_project.active_application
        if target_app:
            app_name = getattr(target_app, 'get_name', lambda: "Unnamed App")()
    except Exception as active_err:
        print("WARN: Could not get active application: %s" % active_err)

    if not target_app:
        try:
            all_children = primary_project.get_children(True)
            for child in all_children:
                if hasattr(child, 'is_application') and child.is_application:
                    target_app = child
                    app_name = getattr(child, 'get_name', lambda: "Unnamed App")()
                    break
        except Exception as find_err:
            print("WARN: Error finding application object: %s" % find_err)

    if not target_app:
        raise RuntimeError("No application found in project '%s'" % project_name)

    messages = _extract_all_messages(target_app, script_engine)
    messages_json, errors, warnings, infos, others = _render_messages_block(messages)

    print("### COMPILE_MESSAGES_START ###")
    print(messages_json)
    print("### COMPILE_MESSAGES_END ###")
    print("Application: %s" % app_name)
    print("Errors: %d" % errors)
    print("Warnings: %d" % warnings)
    print("Infos: %d" % infos)
    print("Others: %d" % others)
    print("Total: %d" % len(messages))
    print("SCRIPT_SUCCESS: Compile messages retrieved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error getting compile messages for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
