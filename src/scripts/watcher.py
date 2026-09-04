"""
Persistent watcher script for CODESYS IPC.

Runs inside CODESYS via --runscript on the primary (UI) thread.
Polls a commands/ directory and executes each command directly on the
primary thread (no marshalling). Yields to the IDE between polls via
``system.delay()``, which serves the message loop and keeps the UI
interactive.

Why no background thread? CODESYS V3.5 SP21+ removed
``system.execute_on_primary_thread()``, the API older versions of this
watcher used to marshal work from a .NET background thread back to the
UI thread. The single-thread design here works on SP19, SP21, and SP22+.

{IPC_BASE_DIR} is interpolated by Node.js before launch.
"""
import sys
import os
import time
import traceback
import json
import codecs

# --- Configuration ---
IPC_BASE_DIR = r"{IPC_BASE_DIR}"
COMMANDS_DIR = os.path.join(IPC_BASE_DIR, "commands")
RESULTS_DIR = os.path.join(IPC_BASE_DIR, "results")
POLL_INTERVAL = 50  # milliseconds
WATCHER_VERSION = "0.4.2"

# --- Error capture file (written before anything else can fail) ---
_ERROR_FILE = os.path.join(IPC_BASE_DIR, "watcher_error.txt")

def _write_error(msg):
    try:
        with open(_ERROR_FILE, "a") as f:
            f.write("[%f] %s\n" % (time.time(), msg))
    except:
        pass

try:
    # --- Ensure directories exist ---
    if not os.path.exists(COMMANDS_DIR):
        os.makedirs(COMMANDS_DIR)
    if not os.path.exists(RESULTS_DIR):
        os.makedirs(RESULTS_DIR)

    def _to_unicode(s):
        try:
            unicode_type = unicode
        except NameError:
            # Python 3. This file targets IronPython 2.7 but stays portable.
            return str(s)

        if isinstance(s, unicode_type):
            return s
        try:
            return unicode_type(s)
        except (UnicodeDecodeError, TypeError, ValueError):
            try:
                return unicode_type(str(s), 'utf-8', 'replace')
            except (UnicodeDecodeError, TypeError, ValueError):
                return unicode_type(repr(s), 'utf-8', 'replace')

    def _json_safe(obj):
        """Normalize a payload to text before it reaches json.dumps().

        Two kinds of byte string reach the result dict under IronPython.
        'output' is joined by OutputCapture from whatever the scripting API
        printed, and 'error' is built at the bottom of execute_script() as a
        plain str from str(e) + traceback.format_exc(). Neither is unicode,
        and on a localized IDE neither is ASCII. Decoding here rather than at
        each construction site covers every field, including ones added later.

        This is not by itself the fix for the localized-output encoding bug
        -- see _encode_result(), which is about the encoder's own behaviour
        rather than the type of what it is handed -- but it is what lets
        ensure_ascii=False emit real text instead of a mojibake round-trip.
        """
        if isinstance(obj, dict):
            return dict((_json_safe(k), _json_safe(v)) for k, v in obj.items())
        if isinstance(obj, (list, tuple)):
            return [_json_safe(v) for v in obj]
        # bool before the numeric passthrough: bool is a subclass of int.
        if obj is None or isinstance(obj, bool):
            return obj

        try:
            unicode_type = unicode
            bytes_type = str          # IronPython 2 / Python 2: str is bytes
        except NameError:
            unicode_type = str        # Python 3
            bytes_type = bytes

        if isinstance(obj, unicode_type):
            return obj
        if isinstance(obj, bytes_type):
            # Try the plausible encodings strictly, in order, before falling
            # back to a lossy decode. latin-1 cannot fail, so the replacement
            # pass is a guarantee rather than a hope.
            for codec in ('utf-8', 'mbcs', 'latin-1'):
                try:
                    return obj.decode(codec)
                except (UnicodeDecodeError, LookupError, TypeError, ValueError):
                    continue
            try:
                return obj.decode('latin-1', 'replace')
            except Exception:
                return _to_unicode(repr(obj))
        return obj                    # ints, floats

    # --- Atomic file write helper ---
    def atomic_write(file_path, content):
        # UTF-8 rather than a plain handle, because _encode_result() emits
        # unicode with ensure_ascii=False. Writing that to a text-mode handle
        # would trigger an implicit ASCII encode and raise, and writing raw
        # high bytes would leave src/ipc.ts -- which reads results as UTF-8 --
        # decoding them into U+FFFD. The encoder and the writer have to agree.
        tmp_path = file_path + ".tmp"
        with codecs.open(tmp_path, "w", "utf-8") as f:
            f.write(_to_unicode(content))
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(file_path):
            os.remove(file_path)
        os.rename(tmp_path, file_path)

    # --- Write ready signal EARLY ---
    ready_path = os.path.join(IPC_BASE_DIR, "ready.signal")
    info = {
        "version": WATCHER_VERSION,
        "python_version": sys.version,
        "platform": sys.platform,
        "ipc_dir": IPC_BASE_DIR,
        "timestamp": time.time(),
        "pid": os.getpid(),
    }
    atomic_write(ready_path, json.dumps(info, indent=2))
    print("[WATCHER] Ready signal written to %s" % ready_path)

    # --- Import scripting engine ---
    _write_error("About to import scriptengine")
    import scriptengine as se
    _write_error("scriptengine imported OK")

    # --- File-based logging ---
    _LOG_FILE = os.path.join(IPC_BASE_DIR, "watcher.log")

    def _log(msg):
        try:
            with open(_LOG_FILE, "a") as f:
                f.write("[%f] %s\n" % (time.time(), msg))
        except:
            pass

    # --- Output Capture ---
    class OutputCapture:
        def __init__(self):
            self._buffer = []
        def write(self, s):
            self._buffer.append(str(s))
        def writelines(self, lines):
            self._buffer.extend([str(l) for l in lines])
        def flush(self):
            pass
        def getvalue(self):
            return ''.join(self._buffer)

    def execute_script(script_code, request_id):
        """Execute script_code synchronously on the current (primary) thread.
        Returns the result dict to be written to results/."""
        success = False
        output = ""
        error = ""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        capture = OutputCapture()
        sys.stdout = capture
        sys.stderr = capture
        try:
            exec_globals = {
                '__builtins__': __builtins__,
                'sys': sys,
                'os': os,
                'time': time,
                'traceback': traceback,
                'shutil': __import__('shutil'),
            }
            exec(script_code, exec_globals)
            output = capture.getvalue()
            if "SCRIPT_ERROR" in output:
                success = False
                error = "Script reported error via SCRIPT_ERROR marker"
            elif "SCRIPT_SUCCESS" in output:
                success = True
            else:
                success = True
        except SystemExit as e:
            output = capture.getvalue()
            exit_code = e.code
            if exit_code is None or exit_code == 0:
                success = True
                if "SCRIPT_ERROR" in output:
                    success = False
                    error = "Script reported error via SCRIPT_ERROR marker"
            elif isinstance(exit_code, int):
                if "SCRIPT_SUCCESS" in output and "SCRIPT_ERROR" not in output:
                    success = True
                else:
                    success = False
                    error = "Script exited with code %s" % exit_code
            elif isinstance(exit_code, str):
                success = False
                error = exit_code
        except KeyboardInterrupt:
            # User pressed "Cancel this operation" in CODESYS during this command.
            # Abort just this command; the watcher loop continues.
            output = capture.getvalue()
            error = "Aborted by user (Cancel pressed in CODESYS)"
            success = False
        except Exception as e:
            output = capture.getvalue()
            error = "%s: %s\n%s" % (type(e).__name__, str(e), traceback.format_exc())
            success = False
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return {
            "requestId": request_id,
            "success": success,
            "output": output,
            "error": error,
            "timestamp": time.time(),
        }

    def _encode_result(result, request_id):
        """Serialize a result dict, degrading to a report rather than raising.

        ensure_ascii is False deliberately, and that is the load-bearing part.
        CODESYS ships its own json library (ScriptLib\\4.1.0.0\\json), whose
        ensure_ascii=True path runs py_encode_basestring_ascii:

            if isinstance(s, str) and HAS_UTF8.search(s) is not None:
                s = s.decode('utf-8')

        Under IronPython the .NET-backed strings coming out of the scripting
        API satisfy isinstance(s, str), and HAS_UTF8 matches any character in
        U+0080..U+00FF -- so a single 'U-umlaut' in localized compiler output
        sends it into a decode against the ANSI codepage that raises
        UnicodeDecodeError. The result file then never gets written and the
        client waits out its whole timeout on a command that in fact
        succeeded. Type coercion cannot dodge this: the value is already text,
        and it is the encoder's own decode that is wrong.

        ensure_ascii=False routes through encode_basestring() instead, which
        escapes and never decodes. atomic_write() emits UTF-8 and the server
        reads results as UTF-8 (src/ipc.ts), so the bytes round-trip intact
        and localized build output survives verbatim.

        A result that still cannot be encoded is worth answering anyway: the
        client learns the command finished and why it could not be reported,
        rather than sitting out the timeout in silence. That fallback payload
        is deliberately pure ASCII so it cannot hit any encoder edge case.
        """
        try:
            return json.dumps(_json_safe(result), ensure_ascii=False)
        except Exception as enc_err:
            _log("Result serialization failed for %s: %s\n%s"
                 % (request_id, enc_err, traceback.format_exc()))
            return json.dumps({
                "requestId": request_id,
                "success": False,
                "output": "",
                "error": "Result could not be serialized; see watcher.log",
                "timestamp": time.time(),
            }, ensure_ascii=True)

    def process_command(command_file):
        """Process a single command file end-to-end on the primary thread."""
        command_path = os.path.join(COMMANDS_DIR, command_file)
        request_id = command_file.replace(".command.json", "")
        result_path = os.path.join(RESULTS_DIR, "%s.result.json" % request_id)

        _log("Processing command: %s" % request_id)

        try:
            with open(command_path, "r") as f:
                command_data = json.loads(f.read())
            script_path = command_data.get("scriptPath", "")
            if not os.path.exists(script_path):
                raise IOError("Script file not found: %s" % script_path)
            with open(script_path, "r") as f:
                script_code = f.read()
        except Exception as read_err:
            _log("Error reading command: %s" % read_err)
            # _encode_result, not json.dumps: "Read error: %s" embeds the
            # script path, and on a localized install that path is itself not
            # ASCII, so the default ensure_ascii=True runs the same decode
            # that raises below. A raise inside this handler would skip the
            # cleanup and hand the loop the same command again.
            try:
                atomic_write(result_path, _encode_result({
                    "requestId": request_id,
                    "success": False,
                    "output": "",
                    "error": "Read error: %s" % read_err,
                    "timestamp": time.time(),
                }, request_id))
            except Exception as write_err:
                _log("Failed to write read-error result for %s: %s"
                     % (request_id, write_err))
            finally:
                _cleanup_command_files(command_path, request_id)
            return

        result = execute_script(script_code, request_id)

        # Everything from here on runs under try/finally, because the command
        # file MUST be removed even if writing the result fails. The main loop
        # picks cmd_files[0] on every iteration: if this function raises, the
        # loop's catch-all logs it and immediately re-processes the *same*
        # command, forever. That is not a stalled command but a hot loop --
        # compile_project rebuilt the project roughly once per second until
        # the server's timeout removed the file, and a side-effecting command
        # (download_to_device, plc_file_delete) would repeat its side effect
        # just as fast. Failing to answer once is recoverable; failing to stop
        # is not.
        try:
            atomic_write(result_path, _encode_result(result, request_id))
            # Report what the script actually produced; _encode_result logs
            # separately if it had to substitute a fallback payload, so these
            # two lines together distinguish "ran and reported" from "ran but
            # could not be reported".
            _log("Result written for %s: script success=%s"
                 % (request_id, result.get("success")))
        except Exception as write_err:
            _log("Failed to write result for %s: %s" % (request_id, write_err))
        finally:
            _cleanup_command_files(command_path, request_id)

    def _cleanup_command_files(command_path, request_id):
        try:
            if os.path.exists(command_path):
                os.remove(command_path)
            sp = os.path.join(COMMANDS_DIR, "%s.py" % request_id)
            if os.path.exists(sp):
                os.remove(sp)
        except:
            pass

    def _terminate_requested():
        return os.path.exists(os.path.join(IPC_BASE_DIR, "terminate.signal"))

    # --- Main loop on the primary thread ---
    print("[WATCHER] Starting watcher v%s (single-thread, primary)" % WATCHER_VERSION)
    print("[WATCHER] IPC directory: %s" % IPC_BASE_DIR)
    print("[WATCHER] Python version: %s" % sys.version)
    _log("Watcher main loop entered")

    def _safe_delay(ms):
        """Yield via system.delay() but swallow KeyboardInterrupt.

        CODESYS injects KeyboardInterrupt into the script when the user
        clicks "Click here to CANCEL this operation" in the IDE. The
        watcher should keep running across that -- only an explicit
        terminate.signal or process kill should stop it.
        """
        try:
            se.system.delay(ms)
        except KeyboardInterrupt:
            _log("KeyboardInterrupt during system.delay() - ignored, watcher continues")

    while True:
        try:
            if _terminate_requested():
                _log("Terminate signal received")
                print("[WATCHER] Terminate signal received, exiting")
                break

            cmd_files = sorted([
                f for f in os.listdir(COMMANDS_DIR)
                if f.endswith(".command.json")
            ])
            if cmd_files:
                process_command(cmd_files[0])
        except KeyboardInterrupt:
            _log("KeyboardInterrupt during loop iteration - ignored, watcher continues")
        except Exception as e:
            _log("Loop error: %s\n%s" % (e, traceback.format_exc()))

        # Yield: serves the message loop so the UI stays interactive.
        _safe_delay(POLL_INTERVAL)

    _log("Watcher main loop exited")

except KeyboardInterrupt:
    # Last-resort: a Cancel that fires before the loop is even reached
    # (e.g. during scriptengine import or directory setup) should still
    # exit quietly without the CODESYS exception dialog.
    _write_error("KeyboardInterrupt outside main loop - exiting quietly")
    print("[WATCHER] Cancelled by user before main loop; exiting.")
except Exception as _fatal:
    _write_error("FATAL: %s\n%s" % (_fatal, traceback.format_exc()))
    print("[WATCHER] FATAL ERROR: %s" % _fatal)
    traceback.print_exc()
