import sys, scriptengine as script_engine, os, traceback

# RTFM (helpme-codesys.com "ScriptLibManObject" + local SP22 stub
# Stubs/scriptengine/ScriptLibManObject.pyi):
#
# - The IDE-level LibManager is injected into the scriptengine scope as the
#   global name `library_manager` and exposes find_library(display_name) ->
#   (ManagedLib, LibRepository) | None for resolving a name against the
#   installed library repositories.
# - The project-level ScriptLibManObject (`lm` below) has TWO add_library
#   overloads:
#       add_library(name: str)       -- ALWAYS adds a placeholder reference
#                                       (resolution is deferred to load time
#                                       and silently fails if the placeholder
#                                       is not registered, bricking the
#                                       project on the next open).
#       add_library(library: ManagedLib)  -- adds a MANAGED reference to a
#                                            specific installed version
#                                            (since 3.5.5.0).
# - lm.references gives back ScriptLibraryReference items. Placeholder refs
#   have .is_placeholder == True, .effective_resolution (a string), and
#   .name == "#<name>". Managed refs have .name == "<Name>, <Version> (<Company>)".
# - lm.remove_library(name) removes a reference by name, accepting either
#   the bare name or the formatted "Name, Version (Company)" string.
#
# Bug being fixed: the prior version of this script called
# lm.add_library(LIBRARY_NAME) with a string. That is the placeholder
# overload and silently produced an unresolvable placeholder if the name
# was not also registered as a placeholder in the IDE. The next open then
# threw "The placeholder library 'X' could not be resolved." and
# script_engine.projects.primary returned None, bricking the project.
#
# Fix:
#   1. Pre-resolve LIBRARY_NAME via library_manager.find_library() and
#      prefer the ManagedLib overload of add_library() so we get a managed
#      reference, not a placeholder.
#   2. Whatever overload was used, walk lm.references after the add and
#      verify the new reference resolved (managed -> just exists; placeholder
#      -> non-empty effective_resolution). If it didn't, call
#      lm.remove_library(LIBRARY_NAME) and refuse to save -- this prevents
#      bricking the next open.

LIBRARY_NAME = "{LIBRARY_NAME}"
USE_DIRECT = "{USE_DIRECT}" == "1"
FORCE_DUP = "{FORCE_DUP}" == "1"
ALLOW_UNRESOLVED = "{ALLOW_UNRESOLVED}" == "1"


# ─── SP-version detection ─────────────────────────────────────────────────
#
# CODESYS reports its build through `sys.version` in the IronPython
# embedding (e.g. "CODESYS V3.5 SP22 Patch 1, ScriptEngine 4.2.0.0").
# Several scriptengine APIs differ across SPs; the version-aware
# dispatchers below switch on this.

def _detect_sp_version():
    """Return (sp_int, patch_int) parsed from sys.version, or (0, 0) if
    not detectable."""
    try:
        sv = sys.version
    except Exception:
        return (0, 0)
    import re as _re
    m = _re.search(r'SP(\d+)(?:\s+Patch\s+(\d+))?', sv)
    if not m:
        return (0, 0)
    try:
        sp = int(m.group(1))
    except Exception:
        sp = 0
    try:
        patch = int(m.group(2)) if m.group(2) else 0
    except Exception:
        patch = 0
    return (sp, patch)


_SP_VERSION = _detect_sp_version()


def _get_lib_manager():
    """Return the IDE-level LibManager instance.

    Per-SP dispatch:
      SP22+: actual attribute is `librarymanager` (one word). The
        Stubs/scriptengine/ScriptLibManObject.pyi documents `library_manager`
        but that name is NOT defined on SP22 -- verified live by probing
        watcher globals 2026-04-29.
      Older SPs: keep the documented `library_manager` name as primary.

    Tries each candidate in scriptengine module + bare globals, returns
    the first that exposes `find_library`."""
    sp, _patch = _SP_VERSION
    if sp >= 22:
        primary_names = ('librarymanager', 'library_manager')
    else:
        primary_names = ('library_manager', 'librarymanager')

    candidates = []
    for nm in primary_names:
        try:
            candidates.append(getattr(script_engine, nm, None))
        except Exception:
            pass
    for nm in primary_names:
        try:
            candidates.append(eval(nm))  # bare global; eval avoids NameError
        except Exception:
            pass

    for cand in candidates:
        if cand is None:
            continue
        if hasattr(cand, 'find_library'):
            return cand
    return None


def _resolve_in_repo_accessible():
    """True iff the IDE-level library manager is accessible AND exposes
    find_library."""
    return _get_lib_manager() is not None


def _find_library_sp22(lm_global, name):
    """SP22 dispatcher for find_library.

    The SP22 stub documents `find_library(display_name: str)` but the
    live API rejects bare strings with 'SystemError: stDisplayName' (the
    C# parameter name) and rejects the kwarg form too. The actual
    working API on SP22, verified live 2026-04-28:

        lm.get_library(name) -> ManagedLib | None
        lm.get_all_libraries() -> iterable[ManagedLib]

    LibRepository on SP22 exposes only `editable`, `name`, `root_folder`
    -- no iteration accessor -- so the old repo-walk path was a dead
    end. Strategy:
      1. get_library(name) -- single direct lookup (preferred).
      2. fall back to get_all_libraries() and filter on default_name /
         displayname / name. default_name is what the IDE Add Library
         dialog uses, so it's the most reliable match key."""
    # Primary: direct lookup by name.
    try:
        hit = lm_global.get_library(name)
        if hit is not None:
            return hit
    except Exception as e:
        print("DEBUG: SP22 get_library(%r) raised: %s: %s -- trying enumerate"
              % (name, type(e).__name__, e))

    # Fallback: enumerate and filter.
    libs = None
    try:
        libs = list(lm_global.get_all_libraries())
    except Exception as e:
        print("DEBUG: SP22 get_all_libraries() raised: %s: %s" % (type(e).__name__, e))
        return None

    candidates = []
    for lib in libs:
        try:
            dn = str(getattr(lib, 'default_name', '') or '')
            disp = str(getattr(lib, 'displayname', '') or '')
            ln = str(getattr(lib, 'name', '') or '')
        except Exception:
            continue
        if (dn == name or disp == name or ln == name
                or dn.startswith(name + ',')
                or disp.startswith(name + ',')
                or ln.startswith(name + ',')):
            candidates.append((dn, disp, ln, lib))

    if candidates:
        print("DEBUG: SP22 get_all_libraries: %d match(es) for %r"
              % (len(candidates), name))
        # Prefer highest displayname (versions sort lexically descending).
        candidates.sort(key=lambda t: t[1], reverse=True)
        return candidates[0][3]
    print("DEBUG: SP22 get_all_libraries: no match for %r across %d lib(s)"
          % (name, len(libs)))
    return None


def _find_library_default(lm_global, name):
    """Pre-SP22 dispatcher: trust the documented stub signature."""
    try:
        result = lm_global.find_library(name)
    except Exception as e:
        print("DEBUG: find_library(%r) raised: %s" % (name, e))
        return None
    if result is None:
        return None
    try:
        return result[0]
    except Exception:
        return result


def _resolve_in_repo(name):
    """Find a ManagedLib by display_name in the installed repository.
    Returns the ManagedLib instance, or None on miss. Dispatches on
    detected SP version because find_library's behaviour differs."""
    lm_global = _get_lib_manager()
    if lm_global is None:
        print("DEBUG: IDE library manager not accessible (tried librarymanager + "
              "library_manager in script_engine and bare globals).")
        return None
    sp, _patch = _SP_VERSION
    if sp >= 22:
        return _find_library_sp22(lm_global, name)
    return _find_library_default(lm_global, name)


def _ref_name_matches(ref_name, target):
    """A managed ref shows up as 'Name, Version (Company)'; a placeholder
    shows up as '#Name'. Match on the bare target name in either form."""
    if ref_name is None:
        return False
    if ref_name == target:
        return True
    if ref_name == ('#' + target):
        return True
    # Managed: leading 'Name, ...'
    if ref_name.startswith(target + ','):
        return True
    return False


def _find_added_reference(lm, target):
    """Walk lm.references and return the entry whose name matches target,
    or None. Used after add to verify resolution."""
    try:
        refs = lm.references
    except Exception as e:
        print("DEBUG: lm.references unavailable: %s" % e)
        return None
    if refs is None:
        return None
    for r in refs:
        try:
            rn = getattr(r, 'name', None)
        except Exception:
            rn = None
        if _ref_name_matches(rn, target):
            return r
    return None


def _is_resolved(ref):
    """Determine whether the reference actually resolves to an installed
    library, not just whether it carries the 'managed' flag.

    Why this is harder than it looks: CODESYS lets you call
    `add_placeholder(name_str)` (or `add_library(name_str)`) for a name
    that is not in the installed Library Repository. The resulting
    reference reports `is_placeholder=False` AND looks structurally
    fine to the script API -- but the IDE's Library Manager shows it
    with a yellow-warning triangle and an empty 'Effective Version'
    column, and any code that touches it fails to compile with
    'placeholder library X could not be resolved'.

    The honest signal is the resolution metadata. A truly resolved
    reference exposes a non-empty version-bearing attribute (one of
    `effective_version`, `resolved_version`, or a non-null
    `resolved_library`). A hollow reference has all of those empty.

    We probe a few attribute names because they vary across SPs."""
    # First: a placeholder is resolved iff its effective_resolution
    # is a non-empty string (this is the older, narrower check that
    # was always correct for placeholders; we keep it).
    try:
        is_ph = bool(getattr(ref, 'is_placeholder', False))
    except Exception:
        is_ph = False
    if is_ph:
        try:
            eff = getattr(ref, 'effective_resolution', None)
        except Exception:
            eff = None
        if eff is None:
            return False
        s = str(eff).strip()
        return len(s) > 0

    # Non-placeholder ('managed') reference: trust ONLY if version /
    # resolved-library metadata is actually present. This is the part
    # that was missing before -- the old code just returned True here
    # and shipped hollow refs.
    version_attrs = (
        'effective_version',
        'resolved_version',
        'version',
    )
    for attr in version_attrs:
        try:
            v = getattr(ref, attr, None)
        except Exception:
            v = None
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() not in ('none', '0.0.0.0', '<none>'):
            return True
    # Try the resolved-library object itself.
    for attr in ('resolved_library', 'managed_library', 'library'):
        try:
            lib = getattr(ref, attr, None)
        except Exception:
            lib = None
        if lib is not None:
            return True
    # Nothing answered; treat as unresolved so the post-add guard
    # backs the change out.
    print("DEBUG: _is_resolved: managed ref appears hollow -- "
          "no effective_version / resolved_library / version metadata. "
          "name=%r, attrs=%s"
          % (getattr(ref, 'name', '?'),
             sorted([a for a in dir(ref) if not a.startswith('_')])[:30]))
    return False


def _try_remove(lm, name):
    """Best-effort removal. SP22 stub documents lm.remove_library(name).
    Some older SPs may not expose it; in that case we surface the
    constraint to the caller via the error message."""
    if not hasattr(lm, 'remove_library'):
        return False, "lm.remove_library not available on this SP"
    try:
        lm.remove_library(name)
        return True, None
    except Exception as e:
        return False, str(e)


try:
    print("DEBUG: add_library script: Library='%s', Project='%s'" % (LIBRARY_NAME, PROJECT_FILE_PATH))
    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if not LIBRARY_NAME:
        raise ValueError("Library name empty.")

    project_name = os.path.basename(PROJECT_FILE_PATH)

    # Find the project's Library Manager via the documented container API
    # (has_library_manager / get_library_manager) -- the same approach
    # list_project_libraries.py uses. The legacy name-search fallback is
    # kept below for SPs that don't expose the marker interface.
    lib_manager = None
    try:
        if hasattr(primary_project, 'has_library_manager') and primary_project.has_library_manager:
            lib_manager = primary_project.get_library_manager()
            print("DEBUG: Found Library Manager via project.get_library_manager()")
    except Exception as e:
        print("DEBUG: project.get_library_manager() failed: %s" % e)

    if not lib_manager:
        # Walk first-level children for a container that has a libman
        # (typically the Application object).
        try:
            for child in primary_project.get_children(False):
                try:
                    if getattr(child, 'has_library_manager', False):
                        lib_manager = child.get_library_manager()
                        if lib_manager is not None:
                            print("DEBUG: Found Library Manager under '%s'" % child.get_name())
                            break
                except Exception:
                    pass
        except Exception as e:
            print("DEBUG: walking children for libman failed: %s" % e)

    if not lib_manager:
        # Last-resort name-search fallback (preserved from prior version).
        try:
            found_list = primary_project.find("Library Manager", True)
            if found_list:
                lib_manager = found_list[0]
                print("DEBUG: Found Library Manager via find('Library Manager') fallback")
        except Exception as e:
            print("DEBUG: find('Library Manager') failed: %s" % e)

    if not lib_manager:
        raise RuntimeError("Library Manager not found in project '%s'." % project_name)

    print("DEBUG: Library Manager found: %s" % getattr(lib_manager, 'get_name', lambda: '?')())

    # Step 0 (NEW per OPEN-BUGS-CROSS-REFERENCE Bug 4): dedup pre-check.
    # If a reference with the same bare name already exists (whether
    # placeholder or managed), no-op with a confirmation message rather
    # than silently creating a duplicate. Bypass with FORCE_DUP=1.
    existing_ref = _find_added_reference(lib_manager, LIBRARY_NAME)
    if existing_ref is not None and not FORCE_DUP:
        existing_name = getattr(existing_ref, 'name', '?')
        is_ph = bool(getattr(existing_ref, 'is_placeholder', False))
        kind = "placeholder" if is_ph else "managed"
        msg = ("Library '%s' is already referenced (%s, name=%r). "
               "No-op (use force=true to add another reference)."
               % (LIBRARY_NAME, kind, existing_name))
        print(msg)
        print("Library Already Present: %s" % LIBRARY_NAME)
        print("Project: %s" % project_name)
        print("SCRIPT_SUCCESS: %s" % msg)
        sys.exit(0)
    if existing_ref is not None and FORCE_DUP:
        print("DEBUG: dedup pre-check found existing reference for '%s' but FORCE_DUP=1 -- adding duplicate." % LIBRARY_NAME)

    # Step 1: pre-resolve the library name against the installed repository.
    # If found, we will pass the ManagedLib to add_library() to get a
    # MANAGED reference instead of a placeholder reference.
    # Distinguish three pre-resolve outcomes:
    #   (a) Found in repo -- proceed; will get a managed reference.
    #   (b) Repo accessible but name NOT found -- HARD REFUSE; this is
    #       the bricking case (add_placeholder creates a hollow ref that
    #       fails next open). Opt-in via ALLOW_UNRESOLVED=1.
    #   (c) Repo access failed (no library_manager global, find_library
    #       missing, etc.) -- can't verify. Proceed cautiously and rely
    #       on the post-add _is_resolved() check; do NOT refuse, because
    #       a successful resolve at the IDE layer would be a false
    #       negative for the user.
    resolved_lib = _resolve_in_repo(LIBRARY_NAME)
    repo_accessible = _resolve_in_repo_accessible()
    if resolved_lib is not None:
        try:
            disp = getattr(resolved_lib, 'displayname', None) or LIBRARY_NAME
        except Exception:
            disp = LIBRARY_NAME
        print("DEBUG: Pre-resolved '%s' to installed library '%s'." % (LIBRARY_NAME, disp))
    elif repo_accessible:
        # (b) -- we could call find_library, it returned no hit.
        print("DEBUG: Pre-resolve via library_manager.find_library returned no hit for '%s'." % LIBRARY_NAME)
        if not ALLOW_UNRESOLVED:
            msg = ("Refused: library '%s' is not installed in the CODESYS library "
                   "repository (library_manager.find_library returned no hit). "
                   "Install it via the Library Repository (Tools > Library Repository, "
                   "or via CODESYS Installer for SL/add-on packages) before re-running, "
                   "or pass allowUnresolved=true if you really want a placeholder for "
                   "a not-yet-installed library."
                   % LIBRARY_NAME)
            print("ERROR: %s" % msg)
            print("SCRIPT_ERROR: %s" % msg)
            sys.exit(1)
        print("DEBUG: ALLOW_UNRESOLVED=1 -- proceeding with placeholder add despite no repo hit.")
    else:
        # (c) -- could not access the IDE-level library manager at all.
        # Don't refuse blindly -- proceed and rely on the post-add
        # _is_resolved() guard at line ~309. If the resulting reference
        # is a hollow placeholder, that guard will catch it and remove.
        print("DEBUG: IDE library_manager not accessible from this script context. "
              "Skipping pre-resolve check; will rely on post-add _is_resolved() guard.")

    # Step 2: add the reference. Default is add_placeholder() to match the
    # modern '<Name>, * (System)' convention (placeholder resolves at
    # compile time so transitive deps stay flexible). USE_DIRECT=1 opts
    # into the legacy direct add_library() path (specific-version pin).
    # Per docs: ScriptLibManObject exposes BOTH add_library(...) and
    # add_placeholder(...) -- see helpme-codesys.com/ScriptLibManObject.
    added = False
    add_attempt_errors = []

    if not USE_DIRECT and hasattr(lib_manager, 'add_placeholder'):
        # Default branch: placeholder add. Try (name, default_resolution)
        # then (name) -- the default_resolution arg lets the IDE record
        # which managed lib the placeholder should resolve to.
        try:
            if resolved_lib is not None:
                try:
                    lib_manager.add_placeholder(LIBRARY_NAME, resolved_lib)
                    added = True
                    print("DEBUG: add_placeholder(name, ManagedLib) succeeded.")
                except Exception as e_pm:
                    add_attempt_errors.append("add_placeholder(name, ManagedLib): %s" % e_pm)
                    print("DEBUG: add_placeholder(name, ManagedLib) failed: %s" % e_pm)
            if not added:
                lib_manager.add_placeholder(LIBRARY_NAME)
                added = True
                print("DEBUG: add_placeholder(name) succeeded.")
        except Exception as e:
            add_attempt_errors.append("add_placeholder(name): %s" % e)
            print("DEBUG: add_placeholder(name) failed: %s" % e)

    # Direct add_library path -- explicit opt-in OR fallback if the IDE
    # doesn't expose add_placeholder.
    if not added and hasattr(lib_manager, 'add_library'):
        if resolved_lib is not None:
            try:
                lib_manager.add_library(resolved_lib)
                added = True
                print("DEBUG: add_library(ManagedLib) succeeded.")
            except Exception as e:
                add_attempt_errors.append("add_library(ManagedLib): %s" % e)
                print("DEBUG: add_library(ManagedLib) failed: %s" % e)
        if not added:
            try:
                lib_manager.add_library(LIBRARY_NAME)
                added = True
                print("DEBUG: add_library(name) succeeded (placeholder overload).")
            except Exception as e:
                add_attempt_errors.append("add_library(name): %s" % e)
                print("DEBUG: add_library(name) failed: %s" % e)

    if not added:
        # Per Bug 4 step 3: detect partial-success state. Neither
        # add_library nor add_placeholder is exposed -- emit a clear
        # error rather than silent-failing.
        api_attrs = []
        try:
            api_attrs = sorted([a for a in dir(lib_manager) if not a.startswith('_')])
        except Exception:
            pass
        raise RuntimeError(
            "Could not add library '%s'. Add overloads failed: %s. lm api: %s"
            % (LIBRARY_NAME,
               "; ".join(add_attempt_errors) or "neither add_library nor add_placeholder on libman",
               ', '.join(api_attrs) if api_attrs else '<dir() empty>'))

    # Step 3: verify the just-added reference actually resolved. If it did
    # not, REMOVE it and refuse to save -- saving an unresolvable
    # placeholder bricks the next project open with
    # "The placeholder library 'X' could not be resolved."
    new_ref = _find_added_reference(lib_manager, LIBRARY_NAME)
    if new_ref is None:
        # Couldn't even find what we added -- safer to back out anything
        # we could have added by name and refuse.
        removed_ok, rem_err = _try_remove(lib_manager, LIBRARY_NAME)
        msg = ("Refused: could not locate the newly added reference for '%s' in lm.references "
               "to verify resolution; backed out (%s) to avoid bricking the project."
               % (LIBRARY_NAME, "removed" if removed_ok else ("removal failed: %s" % rem_err)))
        print("ERROR: %s" % msg)
        print("SCRIPT_ERROR: %s" % msg)
        sys.exit(1)

    if not _is_resolved(new_ref):
        # Unresolvable placeholder. Remove it before save() and report.
        eff = getattr(new_ref, 'effective_resolution', None)
        is_ph = getattr(new_ref, 'is_placeholder', None)
        removed_ok, rem_err = _try_remove(lib_manager, LIBRARY_NAME)
        if not removed_ok:
            msg = ("Refused: library '%s' did not resolve after add (is_placeholder=%s, "
                   "effective_resolution=%r) and the bad reference COULD NOT be removed (%s). "
                   "Project NOT saved. Manually open the Library Manager and remove the "
                   "unresolved reference for '%s' before re-saving."
                   % (LIBRARY_NAME, is_ph, eff, rem_err, LIBRARY_NAME))
        else:
            msg = ("Refused: library '%s' is not installed in the CODESYS library repository "
                   "(would have created an unresolvable placeholder that bricks the next "
                   "project open). The bad reference was removed and the project was NOT "
                   "saved. Install the library via the Library Repository or pass an exact "
                   "installed library name."
                   % LIBRARY_NAME)
        print("ERROR: %s" % msg)
        print("SCRIPT_ERROR: %s" % msg)
        sys.exit(1)

    # Step 4: save only after we have confirmed the reference resolved.
    try:
        ref_name = getattr(new_ref, 'name', '?')
        is_ph = getattr(new_ref, 'is_placeholder', None)
        print("DEBUG: Reference resolved OK -- name=%r, is_placeholder=%s. Saving project..."
              % (ref_name, is_ph))
        primary_project.save()
        print("DEBUG: Project saved successfully after adding library.")
    except Exception as save_err:
        detailed_error = traceback.format_exc()
        error_message = ("Error saving project after adding library '%s': %s\n%s"
                         % (LIBRARY_NAME, save_err, detailed_error))
        print(error_message)
        print("SCRIPT_ERROR: %s" % error_message)
        sys.exit(1)

    print("Library Added: %s" % LIBRARY_NAME)
    print("Project: %s" % project_name)
    print("SCRIPT_SUCCESS: Library added successfully (resolved, managed=%s)."
          % (not bool(getattr(new_ref, 'is_placeholder', False))))
    sys.exit(0)
except Exception as e:
    detailed_error = traceback.format_exc()
    error_message = ("Error adding library '%s' to project '%s': %s\n%s"
                     % (LIBRARY_NAME, PROJECT_FILE_PATH, e, detailed_error))
    print(error_message)
    print("SCRIPT_ERROR: %s" % error_message)
    sys.exit(1)
