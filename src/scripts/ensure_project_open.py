import sys
import scriptengine as script_engine
import os
import time
import traceback

# --- Function to ensure the correct project is open ---
MAX_RETRIES = 3
RETRY_DELAY = 2.0 # seconds (use float for time.sleep)

class DirtyProjectSwitchError(RuntimeError):
    """Switching projects would close a project with unsaved changes.
    Must propagate to the caller -- never swallowed by the retry loop."""
    pass

# Basic path cleanup without excessive escaping
def clean_path(path_str):
    """Clean up a path for CODESYS scripting without excessive escaping"""
    # Simply remove any extraneous quotes
    cleaned = path_str.strip('"\'')
    print("DEBUG: Cleaned path: '%s'" % cleaned)
    return cleaned

def ensure_project_open(target_project_path):
    print("DEBUG: Ensuring project is open: %s" % target_project_path)

    # Just clean the path without adding escapes
    path_to_use = clean_path(target_project_path)

    # Normalize target path once (must match normcase+abspath used on primary_project.path)
    normalized_target_path = os.path.normcase(os.path.abspath(path_to_use))

    for attempt in range(MAX_RETRIES):
        print("DEBUG: Ensure project attempt %d/%d for %s" % (attempt + 1, MAX_RETRIES, normalized_target_path))
        primary_project = None
        try:
            # Getting primary project might fail if CODESYS instance is unstable
            primary_project = script_engine.projects.primary
        except Exception as primary_err:
             print("WARN: Error getting primary project: %s. Assuming none." % primary_err)
             # traceback.print_exc() # Optional: Print stack trace for this error
             primary_project = None

        current_project_path = ""
        project_ok = False # Flag to check if target is confirmed primary and accessible

        if primary_project:
            try:
                # Getting path should be relatively safe if primary_project object exists
                current_project_path = os.path.normcase(os.path.abspath(primary_project.path))
                print("DEBUG: Current primary project path: %s" % current_project_path)
                if current_project_path == normalized_target_path:
                    # Found the right project as primary, now check if it's usable
                    print("DEBUG: Target project path matches primary. Checking access...")
                    try:
                         # Try a relatively safe operation to confirm object usability
                         # Getting children count is a reasonable check
                         _ = len(primary_project.get_children(False))
                         print("DEBUG: Target project '%s' is primary and accessible." % target_project_path)
                         project_ok = True
                         return primary_project # SUCCESS CASE 1: Already open and accessible
                    except Exception as access_err:
                         # Project found, but accessing it failed. Might be unstable.
                         print("WARN: Primary project access check failed for '%s': %s. Will attempt reopen." % (current_project_path, access_err))
                         # traceback.print_exc() # Optional: Print stack trace
                         primary_project = None # Force reopen by falling through
                else:
                    # A *different* project is primary -- close it cleanly
                    # before opening the target. Without this, projects.open
                    # against a different already-primary project tends to
                    # fail (file lock contention) or pop a "project in use"
                    # modal that freezes the IDE thread, breaking every
                    # subsequent script call with 60s timeouts.
                    #
                    # NEVER save the prior primary here. Every modifying MCP
                    # tool saves explicitly after its own change, so a dirty
                    # project at switch time means changes NOBODY asked this
                    # tool to persist (stray IDE edits, another session's
                    # in-flight work). Silently saving them once rewrote a
                    # template project that was only being read as an export
                    # source (Sjobjorn seed, 2026-09-01). If it's dirty,
                    # refuse the switch and make the caller decide.
                    print("DEBUG: Primary project is '%s', not the target '%s'. Closing it before opening target..." % (
                        current_project_path, normalized_target_path))
                    prior_dirty = None
                    try:
                        prior_dirty = bool(primary_project.dirty)
                    except Exception as dirty_err:
                        print("WARN: Could not read dirty flag of prior primary (%s). Assuming clean." % dirty_err)
                    if prior_dirty:
                        raise DirtyProjectSwitchError(
                            "Refusing to switch projects: the currently open project '%s' has UNSAVED changes. "
                            "Save them first (save_project) or discard them (close_project with saveFirst=false), "
                            "then retry opening '%s'. ensure_project_open never saves a project on its own." % (
                                current_project_path, normalized_target_path))
                    try:
                        primary_project.close()
                        print("DEBUG: Closed prior primary '%s'." % current_project_path)
                        # Pump CODESYS so the close transition completes
                        # before we ask it to open something else.
                        try:
                            script_engine.system.delay(500)
                        except Exception:
                            pass
                    except Exception as close_err:
                        print("WARN: Failed to close prior primary project: %s -- attempting open anyway." % close_err)
                    primary_project = None # Force open target project

            except DirtyProjectSwitchError:
                 # Deliberate refusal, not instability -- retrying or falling
                 # through to projects.open would defeat the guard.
                 raise
            except Exception as path_err:
                 # Failed even to get the path of the supposed primary project
                 print("WARN: Could not get path of current primary project: %s. Assuming not the target." % path_err)
                 # traceback.print_exc() # Optional: Print stack trace
                 primary_project = None # Force open target project

        # If target project not confirmed as primary and accessible, attempt to open/reopen
        if not project_ok:
            # Log clearly whether we are opening initially or reopening
            if primary_project is None and current_project_path == "":
                print("DEBUG: No primary project detected. Attempting to open target: %s" % target_project_path)
            elif primary_project is None and current_project_path != "":
                 print("DEBUG: Primary project was '%s' but failed access check or needed close. Attempting to open target: %s" % (current_project_path, target_project_path))
            else: # Includes cases where wrong project was open
                print("DEBUG: Target project not primary or initial check failed. Attempting to open/reopen: %s" % target_project_path)

            try:
                # NoUpdates: don't auto-update libraries on open (would
                # surprise the user / change the project content).
                # We deliberately do NOT pass SilentMode: that flag opens
                # the project into the scriptengine context only and
                # leaves the IDE's project explorer empty, which makes it
                # impossible for the user to see what the MCP is operating
                # on. Without SilentMode the project appears in the IDE
                # tree like a normal File -> Open.
                update_mode = script_engine.VersionUpdateFlags.NoUpdates
                # try:
                #     update_mode = script_engine.VersionUpdateFlags.NoUpdates | script_engine.VersionUpdateFlags.SilentMode
                # except AttributeError:
                #     print("WARN: VersionUpdateFlags not found, using integer flags for open (1 | 2 = 3).")
                #     update_mode = 3 # 1=NoUpdates, 2=SilentMode

                opened_project = None
                try:
                     # The actual open call
                     print("DEBUG: Calling script_engine.projects.open('%s', update_flags=%s)..." % (target_project_path, update_mode))
                     opened_project = script_engine.projects.open(target_project_path, update_flags=update_mode)

                     if not opened_project:
                         # This is a critical failure if open returns None without exception
                         print("ERROR: projects.open returned None for %s on attempt %d" % (target_project_path, attempt + 1))
                         # Allow retry loop to continue
                     else:
                         # Open call returned *something*, let's verify
                         print("DEBUG: projects.open call returned an object for: %s" % target_project_path)
                         print("DEBUG: Pausing for stabilization after open...")
                         time.sleep(RETRY_DELAY)
                         # Re-verify: Is the project now primary and accessible?
                         recheck_primary = None
                         try:
                             recheck_primary = script_engine.projects.primary
                             print("DEBUG: Recheck primary project type: %s" % type(recheck_primary).__name__)
                         except Exception as recheck_primary_err:
                             print("WARN: Error getting primary project after reopen: %s" % recheck_primary_err)
                             traceback.print_exc() # Print full trace for primary project access issue

                         if recheck_primary:
                              recheck_path = ""
                              try: # Getting path might fail
                                  recheck_path = os.path.normcase(os.path.abspath(recheck_primary.path))
                              except Exception as recheck_path_err:
                                  print("WARN: Failed to get path after reopen: %s" % recheck_path_err)

                              if recheck_path == normalized_target_path:
                                   print("DEBUG: Target project confirmed as primary after reopening.")
                                   try: # Final sanity check
                                       _ = len(recheck_primary.get_children(False))
                                       print("DEBUG: Reopened project basic access confirmed.")
                                       return recheck_primary # SUCCESS CASE 2: Successfully opened/reopened
                                   except Exception as access_err_reopen:
                                        print("WARN: Reopened project (%s) basic access check failed: %s." % (normalized_target_path, access_err_reopen))
                                        # traceback.print_exc() # Optional
                                        # Allow retry loop to continue
                              else:
                                   print("WARN: Different project is primary after reopening! Expected '%s', got '%s'." % (normalized_target_path, recheck_path))
                                   # Allow retry loop to continue, maybe it fixes itself
                         else:
                               print("WARN: No primary project found after reopening attempt %d!" % (attempt+1))
                               # Allow retry loop to continue

                except Exception as open_err:
                     # Catch errors during the open call itself
                     print("ERROR: Exception during projects.open call on attempt %d: %s" % (attempt + 1, open_err))
                     traceback.print_exc() # Crucial for diagnosing open failures
                     # Allow retry loop to continue

            except Exception as outer_open_err:
                 # Catch errors in the flag setup etc.
                 print("ERROR: Unexpected error during open setup/logic attempt %d: %s" % (attempt + 1, outer_open_err))
                 traceback.print_exc()

        # If we didn't return successfully in this attempt, wait before retrying
        if attempt < MAX_RETRIES - 1:
            print("DEBUG: Ensure project attempt %d did not succeed. Waiting %f seconds..." % (attempt + 1, RETRY_DELAY))
            time.sleep(RETRY_DELAY)
        else: # Last attempt failed
             print("ERROR: Failed all ensure_project_open attempts for %s." % normalized_target_path)


    # If all retries fail after the loop
    raise RuntimeError("Failed to ensure project '%s' is open and accessible after %d attempts." % (target_project_path, MAX_RETRIES))
# --- End of function ---

# Placeholder for the project file path (must be set in scripts using this snippet)
PROJECT_FILE_PATH = r"{PROJECT_FILE_PATH}"
