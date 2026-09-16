import { describe, it, expect } from 'vitest';
import * as path from 'path';
import * as fs from 'fs';
import { ScriptManager } from '../../src/script-manager';
import { buildRedundancySettings } from '../../src/server';

/**
 * Script-preparation tests for create_redundancy_config, which drives the
 * Automation Platform API of the CODESYS Redundancy add-on from inside the
 * IDE. No CODESYS required.
 */
describe('E2E Script Preparation - create_redundancy_config', () => {
  const scriptsDir = path.join(__dirname, '..', '..', 'src', 'scripts');
  const mgr = new ScriptManager(scriptsDir);
  const HELPERS = ['register_device_credentials', 'ensure_project_open', 'select_application', 'find_object_by_path'];

  const prepare = (overrides: Record<string, string> = {}) => mgr.prepareScriptWithHelpers('create_redundancy_config', {
    PROJECT_FILE_PATH: 'C:\\test.project', APPLICATION_PATH: '""',
    DEVICE_USER: '"u"', DEVICE_PASSWORD: '"p"',
    OBJECT_NAME: '"Redundancy Configuration"', PARENT_PATH: '"PLCWinNT/Plc Logic/Application"',
    SETTINGS_JSON: JSON.stringify(JSON.stringify({ IpAddressPlc1FirstLink: '10.0.0.205', PortFirstLink: 1205, AutoSyncEnabled: true })),
    NON_REDUNDANT_PATHS_JSON: JSON.stringify(JSON.stringify(['Application/GVL_NoSync'])),
    REDUNDANT_PATHS_JSON: JSON.stringify('[]'),
    PLC2_GATEWAY: '"Gateway-1"', PLC2_DEVICE_NAME: '"PFC200V3-4F1A5F"', PLC2_ADDRESS: '""', WRITE_SETTINGS: 'False',
    ...overrides,
  }, HELPERS);

  it('interpolates every placeholder', () => {
    const script = prepare();
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
    expect(script).toContain('OBJECT_NAME = "Redundancy Configuration"');
    expect(script).toContain('PARENT_PATH = "PLCWinNT/Plc Logic/Application"');
    expect(script).toContain('WRITE_SETTINGS = False');
    expect(script).toContain('PLC2_DEVICE_NAME = "PFC200V3-4F1A5F"');
  });

  it('embeds the settings and area lists as JSON string literals', () => {
    const script = prepare();
    expect(script).toContain('SETTINGS = json.loads("{\\"IpAddressPlc1FirstLink\\":\\"10.0.0.205\\",\\"PortFirstLink\\":1205,\\"AutoSyncEnabled\\":true}")');
    expect(script).toContain('NON_REDUNDANT_PATHS = json.loads("[\\"Application/GVL_NoSync\\"]")');
  });

  it('uses the reflected Automation Platform API', () => {
    const script = prepare();
    expect(script).toContain("REDUNDANCY_OBJECT_TYPE = '_3S.CoDeSys.Redundancy.RedundancyObject'");
    expect(script).toContain("REDUNDANCY_TYPE_GUID = '756037c5-9627-47c1-8a26-39d1543fa569'");
    expect(script).toContain("DEVICE_OBJECT_FACTORY_GUID = '84d12aa5-3225-473b-9df6-18af40889bdf'");
    expect(script).toContain("HIDDEN_DEVICE_FLAG = '2'");
    expect(script).toContain("'RedundancyDevice_' + str(red_guid)");
    expect(script).toContain('ro.RegisterNonRedundantArea(obj.guid)');
    expect(script).toContain("'_3S.CoDeSys.Redundancy.SetActivePathPlc2Command'");
    expect(script).toContain("'_3S.CoDeSys.Redundancy.WriteSettingsCommand'");
    expect(script).toContain('om.SetObject(mo, True, None)');
  });

  it('creates the hidden PLC2 device before any online step runs', () => {
    const script = prepare();
    const hidden = script.indexOf('hidden_created = _ensure_hidden_device(');
    const setPath = script.indexOf("_run_batch_command('_3S.CoDeSys.Redundancy.SetActivePathPlc2Command'");
    const write = script.indexOf("_run_batch_command('_3S.CoDeSys.Redundancy.WriteSettingsCommand'");
    expect(hidden).toBeGreaterThan(-1);
    expect(setPath).toBeGreaterThan(hidden);
    expect(write).toBeGreaterThan(setPath);
  });

  it('fails Set Path PLC2 without a bound address and checks both PLCs before Write', () => {
    const script = prepare();
    expect(script).toContain("if not after.get('address'):");
    expect(script).toContain('Set Path PLC2 did not bind a device');
    const check = script.indexOf('_check_devices_reachable(om, handle, red_guid, device_guid)');
    const write = script.indexOf("_run_batch_command('_3S.CoDeSys.Redundancy.WriteSettingsCommand'");
    expect(check).toBeGreaterThan(-1);
    expect(write).toBeGreaterThan(check);
    expect(script).toContain('writeSettings needs the PLC2 path');
  });

  it('reports the write as "command ran", not as verified', () => {
    const script = prepare();
    expect(script).toContain("'writeCommandRan': write_command_ran");
    expect(script).toContain("'writeVerified': False");
    expect(script).not.toContain('settingsWrittenToPlcs');
    expect(script).toContain("'pathSetBy': ('address' if PLC2_ADDRESS else 'scan') if path_set else None");
  });

  it('creates the hidden PLC2 device before committing the object', () => {
    const script = prepare();
    const hidden = script.indexOf('hidden_created = _ensure_hidden_device(');
    const commit = script.indexOf('om.SetObject(mo, True, None)');
    expect(hidden).toBeGreaterThan(-1);
    expect(commit).toBeGreaterThan(hidden);
  });

  it('binds PLC2 by address without a scan when plc2Address is given', () => {
    const script = prepare({ PLC2_ADDRESS: '"127.0.0.1:11746"' });
    expect(script).toContain('PLC2_ADDRESS = "127.0.0.1:11746"');
    expect(script).toContain('def _set_path_plc2_direct');
    expect(script).toContain("t.GetMethod('SetActivePath', flags)");
    expect(script).toContain('_set_path_plc2_direct(handle, device_guid, PLC2_GATEWAY, PLC2_ADDRESS)');
  });

  it('carries the device-credential helper and success markers', () => {
    const script = prepare();
    expect(script).toContain('def register_device_credentials_if_set');
    expect(script).toContain('def find_object_by_path_robust');
    expect(script).toContain('### REDUNDANCY_CONFIG_START ###');
    expect(script).toContain('SCRIPT_SUCCESS');
  });

  it('server.ts registers the tool with applicationPath and the helper chain', () => {
    const server = fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'server.ts'), 'utf-8').replace(/\r\n/g, '\n');
    const i = server.indexOf("\n  s.tool(\n    'create_redundancy_config',");
    expect(i, 'create_redundancy_config registered').toBeGreaterThan(-1);
    const j = server.indexOf('\n  s.tool(\n', i + 20);
    const block = server.substring(i, j);
    expect(block).toContain('applicationPath: z.string().optional().describe(APP_PATH_DESC)');
    expect(block).toContain("['register_device_credentials', 'ensure_project_open', 'select_application', 'find_object_by_path']");
  });

  it('script is ASCII-only (IronPython 2.7 constraint)', () => {
    const src = fs.readFileSync(path.join(scriptsDir, 'create_redundancy_config.py'), 'utf-8');
    // eslint-disable-next-line no-control-regex
    expect(/^[\x00-\x7F]*$/.test(src)).toBe(true);
  });
});

describe('buildRedundancySettings', () => {
  it('maps tool arguments onto IRedundancySettings property names', () => {
    expect(buildRedundancySettings({
      plc1LinkIp: '10.0.0.205', plc2LinkIp: '10.0.0.207', linkPort: 1205, useSecondLink: false,
      taskName: 'MainTask', timeoutMs: 30, syncTimeoutMs: 300, bootUpWaitTimeMs: 5000,
      autoSync: true, dataSyncAlways: false, debugMessages: true, syncTimeTrace: true,
    })).toEqual({
      IpAddressPlc1FirstLink: '10.0.0.205', IpAddressPlc2FirstLink: '10.0.0.207', PortFirstLink: 1205,
      UseSecondLink: false, RedundancyTaskName: 'MainTask', StandbyWaitTime: 30, SyncWaitTime: 300,
      BootUpWaitTime: 5000, AutoSyncEnabled: true, DataSyncAlways: false, DebugMessages: true,
      EnableSyncTimeTrace: true,
    });
  });

  it('maps the second link', () => {
    expect(buildRedundancySettings({ useSecondLink: true, plc1SecondLinkIp: '10.99.99.1', plc2SecondLinkIp: '10.99.99.2', secondLinkPort: 1206 }))
      .toEqual({ UseSecondLink: true, IpAddressPlc1SecondLink: '10.99.99.1', IpAddressPlc2SecondLink: '10.99.99.2', PortSecondLink: 1206 });
  });

  it('leaves out arguments that were not passed, keeping false and 0', () => {
    expect(buildRedundancySettings({})).toEqual({});
    expect(buildRedundancySettings({ autoSync: false, syncTimeoutMs: 0 })).toEqual({ AutoSyncEnabled: false, SyncWaitTime: 0 });
  });
});
