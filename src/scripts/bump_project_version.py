import sys, os, scriptengine as script_engine, traceback, re

# Bumps one part of the 4-part Project Information.version field of the
# primary project. Convention (per CODESYS / 3S / WAGO library practice):
#
#   Major     -- bump on incompatible API break.
#   Minor     -- bump on backward-compatible feature add.
#   Revision  -- bump on bug fix only (no API change).
#   Build     -- internal counter, often 0 for hand-released versions.
#
# Bumping a higher part resets all lower parts to 0 (e.g. bumping minor
# resets revision and build).
#
# The Version field is read/written as a property on the "Project
# Information" node (first child of the primary project). IronPython
# coerces strings like "1.2.3.4" to System.Version automatically; we
# stringify on the read side because str(System.Version) gives
# the dotted form back. None / empty are treated as "0.0.0.0".

LEVEL = "{LEVEL}"  # major | minor | revision | build

# Optional first-run seed override ('' = classic 1.0.0.0). The TS side derives
# it from the latest v* git tag so a project whose Project Information.Version
# was never set does not jump out of an already-tagged release series.
SEED_VERSION = "{SEED_VERSION}"

VALID_LEVELS = ('major', 'minor', 'revision', 'build')

# Standard runtime-readable version anchor. Lives as a constant in a GVL
# under Application so any IEC code can read it as
# _MCP_PROJECT_VERSION.sVersion, and a future read_running_version_online
# tool can pull it via online connect + read_variable. Kept as
# qualified_only so it can't accidentally shadow a same-named local.
VERSION_GVL_NAME = '_MCP_PROJECT_VERSION'
# Plain VAR_GLOBAL (NOT CONSTANT). CODESYS inlines CONSTANT scalars at
# compile time and strips them from the online symbol table, which would
# break read_running_version_online with 'Invalid expression'. Plain
# VAR_GLOBAL keeps the symbol live without needing extra attributes -- a
# verified-working test case in MCPTest2 (GVL_Test.bRun) reads fine over
# the online protocol despite zero IEC references, so a Symbol
# Configuration / 'symbol' attribute is NOT required for the runtime to
# expose unreferenced globals. The string is still effectively read-only
# at runtime since only bump_project_version updates it via
# textual_declaration.replace.
# qualified_only attribute kept so callers must use the full qualified
# name in IEC code (avoids accidental shadowing of a same-named local).
VERSION_GVL_DECLARATION_TEMPLATE = (
    "{attribute 'qualified_only'}\n"
    "VAR_GLOBAL\n"
    "    sVersion : STRING := '%s';\n"
    "END_VAR\n"
)


# --- Library manifest -------------------------------------------------------
# In addition to sVersion, the GVL carries the project's library references
# as one runtime-readable STRING per library where the variable NAME is the
# library namespace and the value is its version (same self-describing style as
# sVersion, plus uiLibraryCount -- NOT an array), so the running PLC reports its
# full library manifest -- not just the app version.
# Refreshed on
# every version bump (the release step), which is the point at which a library
# change should be recorded anyway. (Follow-up: call this same maintenance from
# add_library / remove_library so the manifest also refreshes on a bare lib
# change with no bump -- not yet wired.)
# Enumeration API (verified in list_project_libraries.py): walk the tree for
# nodes whose has_library_manager property is True, then lm.references.

def _lib_safe_get(obj, attr, default=None):
    """getattr that swallows access exceptions and calls callables."""
    try:
        if not hasattr(obj, attr):
            return default
        v = getattr(obj, attr)
        return v() if callable(v) else v
    except Exception:
        return default


def _find_libman_containers(node, depth=0, max_depth=8):
    """Yield every node whose has_library_manager property is True."""
    out = []
    if depth > max_depth:
        return out
    try:
        if hasattr(node, 'has_library_manager'):
            try:
                if node.has_library_manager:
                    out.append(node)
            except Exception:
                pass
    except Exception:
        pass
    try:
        children = node.get_children(False)
    except Exception:
        children = []
    for child in children:
        out.extend(_find_libman_containers(child, depth + 1, max_depth))
    return out


def _ascii_clean(s):
    """Keep only printable ASCII and drop single quotes so the resulting text
    is a valid, single-quote-safe ST string literal (CODESYS source is ASCII)."""
    return ''.join(c for c in s if 32 <= ord(c) < 127 and c != "'")


RESERVED_GVL_NAMES = ('sVersion', 'sDriveFile', 'uiLibraryCount')


def next_drive_file_name(existing_decl, project_file_path):
    """Carry the Drive export name ('<project stem>_NNN', e.g.
    MRCodesysSeaLeopard_BZM_00_006) through version bumps UNCHANGED.
    KK convention update 2026-07-24: the number advances only when a build is
    actually uploaded to Drive (set manually in the GVL at upload time), NOT on
    every bump -- auto-increment per bump burned through numbers for builds that
    never left the machine. Seed '<stem>_001' from the project filename only
    when the variable is absent."""
    m = re.search(r"sDriveFile\s*:\s*STRING\s*:=\s*'([^']*)'", existing_decl or '')
    if m and m.group(1):
        return m.group(1)
    stem = os.path.splitext(os.path.basename(project_file_path))[0]
    return _ascii_clean(stem) + '_001'


def _sanitize_ident(name):
    """Coerce a library namespace into a valid IEC identifier for use as a GVL
    variable name: keep [A-Za-z0-9_], map the rest to '_', and prefix '_' if it
    would start with a digit. Namespaces are normally already valid identifiers
    (they qualify library calls in code); this is a defensive guard."""
    out = []
    for c in name:
        out.append(c if (c.isalnum() or c == '_') else '_')
    s = ''.join(out) or 'Lib'
    if s[0].isdigit():
        s = '_' + s
    return s


def _lib_name_version(ref):
    """Return (identifier, version) for a library reference: identifier from the
    namespace (sanitized to a valid IEC name), version from the effective/default
    resolution string ('CmpApp, 3.5.21.0 (System)' -> '3.5.21.0';
    '* (System)' -> '*'; none found -> '')."""
    raw = _lib_safe_get(ref, 'namespace') or _lib_safe_get(ref, 'name') or ''
    name = _sanitize_ident(_ascii_clean(str(raw)))
    eff = _lib_safe_get(ref, 'effective_resolution') \
        or _lib_safe_get(ref, 'default_resolution') or ''
    ver = ''
    m = re.search(r',\s*(\*|\d+(?:\.\d+){1,3})\s*\(', str(eff))
    if m:
        ver = m.group(1)
    if not ver:
        m2 = re.search(r'(\d+(?:\.\d+){1,3})', str(eff))
        if m2:
            ver = m2.group(1)
    return (name, _ascii_clean(ver))


def enumerate_libraries(primary_project):
    """Return a sorted list of (identifier, version) for every library reference
    across all library-manager containers, de-duplicated by identifier (first
    non-empty version wins). Best-effort: returns [] on any failure so the
    version bump still succeeds."""
    by_name = {}
    try:
        for container in _find_libman_containers(primary_project):
            try:
                lm = container.get_library_manager()
            except Exception:
                continue
            try:
                refs = lm.references
            except Exception:
                continue
            try:
                for ref in refs:
                    name, ver = _lib_name_version(ref)
                    if not name or name in RESERVED_GVL_NAMES:
                        continue
                    if name not in by_name or (not by_name[name] and ver):
                        by_name[name] = ver
            except Exception:
                pass
    except Exception:
        pass
    return sorted(by_name.items())


def build_version_gvl_declaration(version_str, libraries, drive_file=''):
    """Build the _MCP_PROJECT_VERSION GVL: the sVersion anchor plus the library
    manifest as one scalar STRING per reference, where the VARIABLE NAME is the
    library namespace and the value is its resolved version (same self-describing
    style as sVersion -- each individually readable over the online protocol).
    uiLibraryCount holds the number of library entries."""
    lines = [
        "{attribute 'qualified_only'}",
        "VAR_GLOBAL",
        "    sVersion : STRING := '%s';" % version_str,
        "    // Drive export name for THIS build (maintained by bump_project_version;",
        "    // incremented on every version bump - gaps mean a version was never",
        "    // uploaded). The running PLC reports which Drive file it came from.",
        "    sDriveFile : STRING := '%s';" % drive_file,
        "    // Library manifest - one STRING per library: the variable NAME is the",
        "    // library namespace, the value its resolved version. Maintained by",
        "    // bump_project_version.",
        "    uiLibraryCount : UINT := %d;" % len(libraries),
    ]
    for name, ver in libraries:
        lines.append("    %s : STRING := '%s';" % (name, ver[:79]))
    lines.append("END_VAR")
    lines.append("")
    return "\n".join(lines)


def parse_version(v):
    """Parse a version-like value into a 4-tuple of ints, defaulting missing
    parts to 0. Accepts None, '', '1.2', '1.2.3', '1.2.3.4', or a
    System.Version. Raises ValueError on anything that can't be parsed."""
    if v is None:
        return (0, 0, 0, 0)
    s = str(v).strip()
    if not s or s == 'None':
        return (0, 0, 0, 0)
    parts = s.split('.')
    if len(parts) > 4:
        raise ValueError("version '%s' has more than 4 parts" % s)
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            raise ValueError("version '%s' has non-integer part '%s'" % (s, p))
    while len(nums) < 4:
        nums.append(0)
    return tuple(nums)


def read_version_from_gvl(primary_project):
    """When Project Information is missing, read the current version back
    from the runtime anchor GVL (_MCP_PROJECT_VERSION.sVersion) so subsequent
    bumps can resume from the actual current state instead of re-seeding to
    1.0.0.0 on every call. Returns the version string or None if the GVL
    doesn't exist yet (true first-run)."""
    try:
        app = getattr(primary_project, 'active_application', None)
    except Exception:
        app = None
    if app is None:
        try:
            apps = primary_project.find('Application', True)
            if apps:
                app = apps[0]
        except Exception:
            pass
    if app is None:
        return None
    try:
        for child in app.get_children(False):
            try:
                if child.get_name() != VERSION_GVL_NAME:
                    continue
                decl = child.textual_declaration.text or ''
                m = re.search(r"sVersion\s*:\s*STRING\s*:=\s*'(\d+\.\d+\.\d+\.\d+)'", decl)
                if m:
                    return m.group(1)
                return None
            except Exception:
                pass
    except Exception:
        pass
    return None


def _all_applications(primary_project):
    """Every application in the project - multi-device projects have one per
    device. Falls back to the active application when the walk finds none."""
    apps = []
    try:
        for c in primary_project.get_children(True):
            try:
                if getattr(c, 'is_application', False):
                    apps.append(c)
            except Exception:
                pass
    except Exception as e:
        print("WARNING: walking project for applications failed: %s" % e)
    if not apps:
        try:
            app = getattr(primary_project, 'active_application', None)
            if app is not None:
                apps.append(app)
        except Exception:
            pass
    return apps


def maintain_version_gvl(primary_project, version_str):
    """Maintain the _MCP_PROJECT_VERSION GVL in EVERY application of the
    project. The version is project-wide, and in a multi-device project each
    PLC must carry it so read_running_version_online works against any of
    them. Returns True only if every application succeeded."""
    apps = _all_applications(primary_project)
    if not apps:
        print("WARNING: no Application found - cannot maintain %s GVL" % VERSION_GVL_NAME)
        return False
    ok = True
    for app in apps:
        try:
            label = app.get_name()
        except Exception:
            label = 'Application'
        print("DEBUG: maintaining %s in application '%s'" % (VERSION_GVL_NAME, label))
        if not _maintain_version_gvl_in_app(primary_project, app, version_str):
            ok = False
    return ok


def _maintain_version_gvl_in_app(primary_project, app, version_str):
    """Find or create the _MCP_PROJECT_VERSION GVL under ONE Application and
    set its declaration so the running PLC carries the project version as a
    constant string. Soft-fails on any error - the primary outcome of the
    bump (Project Information.Version) has already succeeded by the time
    this is called, so a GVL creation failure is logged as a WARNING but
    does not fail the whole tool."""

    # Try to find existing GVL with this name (also the source of the previous
    # sDriveFile value, which the new declaration increments)
    existing = None
    try:
        for child in app.get_children(False):
            try:
                if child.get_name() == VERSION_GVL_NAME:
                    existing = child
                    break
            except Exception:
                pass
    except Exception as e:
        print("WARNING: walking Application children failed: %s" % e)

    existing_decl = ''
    if existing is not None:
        try:
            existing_decl = existing.textual_declaration.text or ''
        except Exception:
            pass
    drive_file = next_drive_file_name(existing_decl, PROJECT_FILE_PATH)
    libraries = enumerate_libraries(primary_project)
    decl = build_version_gvl_declaration(version_str, libraries, drive_file)
    print("DEBUG: library manifest: %d reference(s) enumerated for %s" % (
        len(libraries), VERSION_GVL_NAME))
    print("DEBUG: sDriveFile -> '%s'" % drive_file)

    if existing is not None:
        try:
            existing.textual_declaration.replace(decl)
            print("DEBUG: updated %s -> sVersion := '%s'" % (VERSION_GVL_NAME, version_str))
            return True
        except Exception as e:
            print("WARNING: failed to update existing %s declaration: %s" % (VERSION_GVL_NAME, e))
            return False

    # Create it
    if not hasattr(app, 'create_gvl'):
        print("WARNING: Application object doesn't expose create_gvl -- cannot create %s" % VERSION_GVL_NAME)
        return False
    try:
        new_gvl = app.create_gvl(name=VERSION_GVL_NAME)
        if new_gvl is None:
            print("WARNING: create_gvl returned None for %s" % VERSION_GVL_NAME)
            return False
        new_gvl.textual_declaration.replace(decl)
        print("DEBUG: created %s with sVersion := '%s'" % (VERSION_GVL_NAME, version_str))
        return True
    except Exception as e:
        print("WARNING: failed to create %s: %s" % (VERSION_GVL_NAME, e))
        return False


def bump(parts, level):
    major, minor, revision, build = parts
    if level == 'major':
        return (major + 1, 0, 0, 0)
    if level == 'minor':
        return (major, minor + 1, 0, 0)
    if level == 'revision':
        return (major, minor, revision + 1, 0)
    if level == 'build':
        return (major, minor, revision, build + 1)
    raise ValueError("unknown bump level '%s' (must be one of %s)" % (level, ', '.join(VALID_LEVELS)))


try:
    if LEVEL not in VALID_LEVELS:
        raise ValueError("level must be one of %s, got '%s'" % (', '.join(VALID_LEVELS), LEVEL))

    primary_project = ensure_project_open(PROJECT_FILE_PATH)
    if 'apply_application_selection' in globals():
        apply_application_selection(primary_project)

    # Find the Project Information node via the official is_project_info
    # marker rather than name-matching. Walk the project tree -- the node is
    # usually at the root, but locating it via the marker is robust against
    # localised IDE display names ('Projektinformation' in DE, etc.) and
    # against projects where the node lives at a different depth.
    pi = None
    def _find_pi(node, depth=0, max_depth=4):
        if depth > max_depth:
            return None
        try:
            if getattr(node, 'is_project_info', False):
                return node
        except Exception:
            pass
        try:
            for c in node.get_children(False):
                hit = _find_pi(c, depth + 1, max_depth)
                if hit is not None:
                    return hit
        except Exception:
            pass
        return None
    pi = _find_pi(primary_project)

    # Some projects (notably ones created from the Standard template via the
    # scripting create_project flow) have no Project Information node at all
    # -- the IDE adds it lazily the first time the user opens
    # Project menu -> Project Information. We don't have a documented way to
    # create one via scripting, so handle it gracefully: skip the metadata
    # write but still maintain the runtime-readable GVL, which is the
    # source-of-truth at runtime anyway. The user can add Project Information
    # manually via the IDE later if they want the metadata side too.
    pi_missing = pi is None
    if pi_missing:
        print("WARNING: Project Information node not found in project tree -- "
              "skipping metadata write. The runtime anchor (GVL) will still be "
              "maintained. To add the Project Information node, open the "
              "Project menu -> Project Information in the IDE; subsequent bumps "
              "will then update both metadata and GVL.")
        # Fall back to reading the existing GVL so we resume from the actual
        # current version instead of re-seeding to 1.0.0.0 every call.
        before_raw = read_version_from_gvl(primary_project)
        if before_raw:
            print("DEBUG: Project Information missing, resuming from GVL: %s" % before_raw)
    else:
        # Cross-check pi.version against the runtime-anchor GVL and take the
        # max of the two as the resume point. Drift between the two sides
        # happens when a release is finished by an external (non-MCP) script
        # that updates one but not the other -- the GVL gets refreshed via
        # inject-once writes, and pi.version gets refreshed via direct .project
        # binary edits, but a script that touches only one leaves the other
        # stale. Without the cross-check, the next bump would silently regress
        # the version (observed: pi.version stuck at 1.0.0.0 while GVL was at
        # 1.2.1.0 -> minor bump gave 1.1.0.0, colliding with an existing tag).
        # Taking the max is always safe: the GVL only ever moves forward (set
        # by maintain_version_gvl on every bump), and pi.version only ever
        # moves forward (set by pi.version assignment). The higher of the
        # two is the true latest version regardless of which side drifted.
        pi_raw = pi.version
        gvl_raw = read_version_from_gvl(primary_project)
        pi_parts = parse_version(pi_raw) if pi_raw is not None else (0, 0, 0, 0)
        gvl_parts = parse_version(gvl_raw) if gvl_raw else (0, 0, 0, 0)
        if pi_parts >= gvl_parts:
            before_raw = pi_raw
        else:
            print("WARNING: Project Information.Version (%s) is BEHIND the runtime anchor "
                  "GVL (%s) -- this happens when a previous release was finished by an "
                  "external script that updated the GVL but not the .project metadata. "
                  "Using the GVL value as the resume point so the bump doesn't regress." % (
                      pi_raw, gvl_raw))
            before_raw = gvl_raw
            # Heal pi.version forward to the GVL value before the bump so this
            # warning doesn't recur on the next call.
            try:
                pi.version = gvl_raw
                print("DEBUG: healed Project Information.Version: %s -> %s (matching GVL)" % (
                    pi_raw, gvl_raw))
            except Exception as heal_e:
                print("WARNING: could not heal Project Information.Version: %s" % heal_e)
    before_str = str(before_raw) if before_raw is not None else None

    # First-run convention: if no version is set yet, seed at 1.0.0.0 instead
    # of treating "no version" as 0.0.0.0 + bump (which would give 0.0.0.1
    # for level=build, awkward for a first canonical version). Most projects
    # start tracking at 1.0.0.0 when they first turn on versioning, and the
    # level argument is moot for the seed step.
    seed_check = parse_version(before_raw)
    if seed_check == (0, 0, 0, 0) and (before_raw is None or str(before_raw).strip() in ('', '0.0.0.0', 'None')):
        # Prefer the tag-derived seed when the TS side found a v* release tag,
        # so a project with an unset Project Information.Version stays in its
        # already-tagged series instead of jumping to 1.0.0.0. Guard against an
        # unsubstituted placeholder for safety with older callers.
        seed_str = SEED_VERSION.strip()
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', seed_str):
            after_parts = parse_version(seed_str)
            after_str = seed_str
            print("DEBUG: bump_project_version: no prior version -- seeding to %s from latest v* git tag (level=%s applied to the tag)" % (after_str, LEVEL))
        else:
            after_parts = (1, 0, 0, 0)
            after_str = '1.0.0.0'
            print("DEBUG: bump_project_version: no prior version -- seeding to 1.0.0.0 (level=%s ignored on first run)" % LEVEL)
    else:
        before_parts = seed_check
        after_parts = bump(before_parts, LEVEL)
        after_str = '%d.%d.%d.%d' % after_parts
        print("DEBUG: bump_project_version: level=%s before=%s -> after=%s" % (
            LEVEL, before_str, after_str))

    if not pi_missing:
        pi.version = after_str

    # Maintain the runtime-readable version anchor (_MCP_PROJECT_VERSION GVL)
    # so the running PLC carries the same string. Soft-fails so the primary
    # bump still reports success even if GVL creation hits an edge case.
    gvl_ok = maintain_version_gvl(primary_project, after_str)

    try:
        primary_project.save()
        print("DEBUG: project.save() succeeded after version bump.")
    except Exception as save_e:
        print("WARNING: project.save() raised %s -- bump applied in memory but may not persist across IDE close." % save_e)

    if pi_missing:
        print("Project Information.Version: (skipped -- node missing) -> %s" % after_str)
    else:
        print("Project Information.Version: %s -> %s" % (before_str, after_str))
    if gvl_ok:
        print("Runtime anchor: %s.sVersion := '%s'" % (VERSION_GVL_NAME, after_str))
    else:
        print("Runtime anchor: %s NOT updated (see WARNING above)" % VERSION_GVL_NAME)
    print("SCRIPT_SUCCESS: bump_project_version complete.")
    sys.exit(0)
except Exception as e:
    detailed = traceback.format_exc()
    msg = "Error in bump_project_version for project '%s': %s\n%s" % (
        PROJECT_FILE_PATH, e, detailed)
    print(msg)
    print("SCRIPT_ERROR: %s" % msg)
    sys.exit(1)
