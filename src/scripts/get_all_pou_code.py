import sys, scriptengine as script_engine, os, traceback, json

try:
    print("DEBUG: get_all_pou_code script: Project='%s'" % PROJECT_FILE_PATH)
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    project_name = os.path.basename(PROJECT_FILE_PATH)

    all_code = []

    # ------------------------------------------------------------------
    # Why this file does not use json.dumps
    #
    # IronPython 2.7's json encoder starts py_encode_basestring_ascii with
    #     if isinstance(s, str) and HAS_UTF8.search(s) is not None:
    #         s = s.decode('utf-8')
    # and in IronPython `isinstance(u'x', str)` is True -- str and unicode both
    # wrap System.String. So any POU text containing a non-ASCII character
    # (degree sign, plus-minus, box-drawing in a comment banner) takes that
    # branch, the lone high byte is not valid UTF-8, and the whole dump dies
    # with UnicodeDecodeError. Coercing the type does not help; the isinstance
    # check passes either way.
    #
    # Writing the JSON ourselves sidesteps it: we escape every non-ASCII char
    # to \\uXXXX before it can reach that code path. Output is byte-identical
    # to what CPython's json.dumps would produce, so the TypeScript side needs
    # no changes.
    # ------------------------------------------------------------------

    _ESCAPES = {
        u'"': u'\\"',
        u'\\': u'\\\\',
        u'\b': u'\\b',
        u'\f': u'\\f',
        u'\n': u'\\n',
        u'\r': u'\\r',
        u'\t': u'\\t',
    }

    def _jstr(s):
        """Render a value as an ASCII-only JSON string literal."""
        if s is None:
            s = u""
        if not isinstance(s, basestring):
            s = unicode(s)
        out = [u'"']
        for ch in s:
            esc = _ESCAPES.get(ch)
            if esc is not None:
                out.append(esc)
                continue
            o = ord(ch)
            if o < 0x20 or o > 0x7E:
                # Covers control chars and everything non-ASCII. Strings are
                # UTF-16 here, so astral chars arrive as two surrogates and
                # emit as two \\uXXXX escapes -- which is valid JSON.
                out.append(u'\\u%04x' % o)
            else:
                out.append(ch)
        out.append(u'"')
        return u''.join(out)

    def _jobj(entry, keys):
        """Render a dict as a JSON object, keys in the given order."""
        pairs = [u'%s:%s' % (_jstr(k), _jstr(entry[k])) for k in keys if k in entry]
        return u'{%s}' % u','.join(pairs)

    def collect_code(obj, path_prefix):
        """Recursively collect code from all objects that have textual content."""
        obj_name = getattr(obj, 'get_name', lambda: '?')()
        current_path = "%s/%s" % (path_prefix, obj_name) if path_prefix else obj_name

        entry = None

        # Check for textual declaration
        decl_text = ""
        if hasattr(obj, 'textual_declaration'):
            try:
                td = obj.textual_declaration
                if td and hasattr(td, 'text'):
                    decl_text = td.text or ""
            except Exception:
                pass

        # Check for textual implementation
        impl_text = ""
        if hasattr(obj, 'textual_implementation'):
            try:
                ti = obj.textual_implementation
                if ti and hasattr(ti, 'text'):
                    impl_text = ti.text or ""
            except Exception:
                pass

        if decl_text or impl_text:
            entry = {
                'path': current_path,
                'type': type(obj).__name__,
            }
            if decl_text:
                entry['declaration'] = decl_text
            if impl_text:
                entry['implementation'] = impl_text
            all_code.append(entry)

        # Recurse into children
        try:
            children = obj.get_children(False)
            for child in children:
                collect_code(child, current_path)
        except Exception:
            pass

    # Start from project root
    try:
        root_children = primary_project.get_children(False)
        for child in root_children:
            collect_code(child, "")
    except Exception as e:
        print("WARN: Error traversing project tree: %s" % e)

    _KEY_ORDER = ['path', 'type', 'declaration', 'implementation']
    code_json = u'[%s]' % u','.join(_jobj(e, _KEY_ORDER) for e in all_code)
    print("### ALL_POU_CODE_START ###")
    print(code_json)
    print("### ALL_POU_CODE_END ###")
    print("Total POUs with code: %d" % len(all_code))
    print("SCRIPT_SUCCESS: All POU code retrieved.")
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = "Error getting all POU code for project %s: %s\n%s" % (PROJECT_FILE_PATH, e, detailed_error)
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
