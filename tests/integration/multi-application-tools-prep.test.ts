import { describe, it, expect } from 'vitest';
import * as path from 'path';
import * as fs from 'fs';
import { ScriptManager } from '../../src/script-manager';

/**
 * Script-preparation tests for multi-device / multi-application support:
 * the select_application helper, the list_applications and
 * set_active_application tools, and the APPLICATION_PATH hook threaded
 * through the build / online / version scripts. No CODESYS required.
 */
describe('E2E Script Preparation - multi-application tools', () => {
  const scriptsDir = path.join(__dirname, '..', '..', 'src', 'scripts');
  const mgr = new ScriptManager(scriptsDir);
  const P = { PROJECT_FILE_PATH: 'C:\\test.project', APPLICATION_PATH: '"Master/Plc Logic/Application"' };
  const NONE = { PROJECT_FILE_PATH: 'C:\\test.project', APPLICATION_PATH: '""' };
  const SEL = ['ensure_project_open', 'select_application'];
  const ONLINE = ['ensure_project_open', 'select_application', 'ensure_online_connection'];

  it('select_application helper defines the resolver API and interpolates APPLICATION_PATH', () => {
    const script = mgr.prepareScriptWithHelpers('list_applications', P, SEL);
    expect(script).toContain('def enumerate_applications');
    expect(script).toContain('def select_application');
    expect(script).toContain('def apply_application_selection');
    expect(script).toContain('def application_full_path');
    expect(script).toContain('def device_of_application');
    expect(script).toContain('primary_project.active_application = chosen');
    expect(script).toContain('APPLICATION_PATH = "Master/Plc Logic/Application"');
    expect(script).not.toContain('{APPLICATION_PATH}');
  });

  it('list_applications prepares with JSON markers', () => {
    const script = mgr.prepareScriptWithHelpers('list_applications', NONE, SEL);
    expect(script).toContain('### APPLICATIONS_START ###');
    expect(script).toContain('### APPLICATIONS_END ###');
    expect(script).toContain('SCRIPT_SUCCESS');
  });

  it('set_active_application prepares, saves and reports before/after', () => {
    const script = mgr.prepareScriptWithHelpers('set_active_application', P, SEL);
    expect(script).toContain('select_application(primary_project, APPLICATION_PATH)');
    expect(script).toContain('primary_project.save()');
    expect(script).toContain('### ACTIVE_APPLICATION_START ###');
    expect(script).toContain('SCRIPT_SUCCESS');
  });

  it('build-side scripts call the selection hook right after ensure_project_open', () => {
    for (const name of ['compile_project', 'get_compile_messages', 'application_build_action',
      'check_online_change', 'create_boot_application', 'bump_project_version',
      'verify_device_reachable', 'rebind_device_to_scan']) {
      const src = fs.readFileSync(path.join(scriptsDir, `${name}.py`), 'utf-8');
      const hook = src.indexOf("if 'apply_application_selection' in globals():");
      const open = src.indexOf('primary_project = ensure_project_open(PROJECT_FILE_PATH)');
      expect(hook, `${name} missing hook`).toBeGreaterThan(-1);
      expect(hook, `${name} hook must follow ensure_project_open`).toBeGreaterThan(open);
      // exactly one hook per script
      expect(src.split("apply_application_selection(primary_project)").length - 1, `${name} hook count`).toBe(1);
    }
  });

  it('ensure_online_connection honours the selection and prefers the target app device', () => {
    const script = mgr.prepareScriptWithHelpers('read_variable',
      { ...P, VARIABLE_PATH: 'PLC_PRG.x' }, ONLINE);
    expect(script).toContain("if 'apply_application_selection' in globals():");
    expect(script).toContain('_ensure_device_connected(primary_project, target_app)');
    expect(script).toContain('def _ensure_device_connected(primary_project, target_app=None)');
    expect(script).toContain('using the one hosting the target application');
  });

  it('scripts still prepare WITHOUT the helper (hook is guarded)', () => {
    // Single-device callers / older helper lists must keep working: the hook
    // is a globals() check, so the helper is optional.
    const script = mgr.prepareScriptWithHelpers('compile_project',
      { PROJECT_FILE_PATH: 'C:\\test.project' }, ['ensure_project_open']);
    expect(script).not.toContain('def apply_application_selection');
    expect(script).toContain("if 'apply_application_selection' in globals():");
    expect(script).not.toContain('{APPLICATION_PATH}');
  });

  it('find_target_device prefers the device hosting the active application', () => {
    const script = mgr.prepareScriptWithHelpers('verify_device_reachable', P,
      ['ensure_project_open', 'select_application', 'find_target_device']);
    expect(script).toContain('def _device_hosting_active_application');
    expect(script).toContain('hosts the active application');
  });

  it('bump_project_version maintains the version GVL in every application', () => {
    const script = mgr.prepareScriptWithHelpers('bump_project_version',
      { ...P, LEVEL: 'build', DEFAULT_START_VERSION: '1.0.0.0' }, SEL);
    expect(script).toContain('def _all_applications');
    expect(script).toContain('def maintain_version_gvl(primary_project, version_str)');
    expect(script).toContain('def _maintain_version_gvl_in_app(primary_project, app, version_str)');
    expect(script).toContain("_maintain_version_gvl_in_app(primary_project, app, version_str)");
  });

  it('task, library and symbol-config tools resolve against the active application first', () => {
    for (const name of ['list_tasks', 'add_pou_to_task', 'remove_pou_from_task']) {
      const src = fs.readFileSync(path.join(scriptsDir, `${name}.py`), 'utf-8');
      expect(src, name).toContain('tc = find_task_config(_app)');
      expect(src, name).toContain('tc = find_task_config(primary_project)');
    }
    for (const name of ['create_task', 'configure_task']) {
      const src = fs.readFileSync(path.join(scriptsDir, `${name}.py`), 'utf-8');
      expect(src, name).toContain('_scopes.append(_app)');
      expect(src, name).toContain('_scopes.append(primary_project)');
    }
    for (const name of ['add_library', 'remove_library']) {
      const src = fs.readFileSync(path.join(scriptsDir, `${name}.py`), 'utf-8');
      expect(src, name).toContain('Using Library Manager of the active application');
      expect(src, name).toContain("if not lib_manager and hasattr(primary_project, 'has_library_manager')");
    }
    const sym = fs.readFileSync(path.join(scriptsDir, 'find_symbol_config_object.py'), 'utf-8');
    expect(sym).toContain('in_app = find_all_symbol_config_objects(app)');
    const dev = fs.readFileSync(path.join(scriptsDir, 'find_device_object.py'), 'utf-8');
    expect(dev).toContain('node = primary_project.active_application');
    const udt = fs.readFileSync(path.join(scriptsDir, 'update_device_type.py'), 'utf-8');
    expect(udt).toContain('_routed_device_of_active_application(project) or _find_first_routed_device(project)');
    const adu = fs.readFileSync(path.join(scriptsDir, 'add_device_user.py'), 'utf-8');
    expect(adu).toContain('node = primary_project.active_application');
  });

  it('every hooked script calls the selection hook exactly once', () => {
    for (const name of ['list_tasks', 'add_pou_to_task', 'remove_pou_from_task', 'create_task', 'configure_task',
      'add_library', 'remove_library', 'create_pou', 'create_dut', 'create_gvl', 'create_folder',
      'scan_network_devices', 'find_symbol_config', 'list_all_signatures', 'list_all_datatypes',
      'list_configured_symbols', 'get_symbol_config_settings', 'set_symbol_config_settings',
      'set_symbol_access', 'set_signature_access_bulk', 'export_symbol_xsd', 'add_device_user',
      'update_device_type', 'ensure_online_connection']) {
      const src = fs.readFileSync(path.join(scriptsDir, `${name}.py`), 'utf-8');
      expect(src.split('apply_application_selection(').length - 1, name).toBe(1);
    }
  });

  it('server.ts wires applicationPath on every application-scoped tool', () => {
    const server = fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'server.ts'), 'utf-8').replace(/\r\n/g, '\n');
    for (const tool of ['compile_project', 'get_compile_messages', 'application_build', 'check_online_change',
      'create_boot_application', 'connect_to_device', 'disconnect_from_device', 'get_application_state',
      'read_variable', 'write_variable', 'reset_application', 'read_variables', 'write_variables',
      'force_variables', 'unforce_variables', 'list_forced_variables', 'source_download', 'source_upload',
      'plc_file_list', 'plc_file_transfer', 'plc_file_delete', 'download_to_device', 'start_stop_application',
      'read_running_version_online', 'bump_project_version', 'verify_device_reachable',
      'rebind_device_to_scan_result',
      'list_tasks', 'add_pou_to_task', 'remove_pou_from_task', 'create_task', 'configure_task',
      'add_library', 'remove_library', 'create_pou', 'create_dut', 'create_gvl', 'create_folder',
      'scan_network_devices', 'find_symbol_config', 'list_all_signatures', 'list_all_datatypes',
      'list_configured_symbols', 'get_symbol_config_settings', 'set_symbol_config_settings',
      'set_symbol_access', 'set_signature_access_bulk', 'export_symbol_xsd', 'add_device_user',
      'update_device_type']) {
      const i = server.indexOf(`\n  s.tool(\n    '${tool}',`);
      expect(i, `${tool} registered`).toBeGreaterThan(-1);
      const j = server.indexOf('\n  s.tool(\n', i + 20);
      const block = server.substring(i, j === -1 ? server.length : j);
      expect(block, `${tool} schema`).toContain('applicationPath: z.string().optional().describe(APP_PATH_DESC)');
      expect(block, `${tool} args type`).toContain('applicationPath?: string;');
    }
    expect(server).toContain("'list_applications',");
    expect(server).toContain("'set_active_application',");
    expect(server).toContain("const ONLINE_HELPERS = ['ensure_project_open', 'select_application', 'ensure_online_connection'];");
  });

  it('new scripts are ASCII-only (IronPython 2.7 constraint)', () => {
    for (const name of ['select_application', 'list_applications', 'set_active_application']) {
      const src = fs.readFileSync(path.join(scriptsDir, `${name}.py`), 'utf-8');
      // eslint-disable-next-line no-control-regex
      expect(/^[\x00-\x7F]*$/.test(src), `${name} non-ASCII`).toBe(true);
    }
  });
});
