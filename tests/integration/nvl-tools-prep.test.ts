import { describe, it, expect } from 'vitest';
import * as path from 'path';
import * as fs from 'fs';
import { ScriptManager } from '../../src/script-manager';

/**
 * Script-preparation tests for the Network Variable List tools, which use
 * the Automation Platform API from inside the IDE. No CODESYS required.
 */
describe('E2E Script Preparation - NVL tools', () => {
  const scriptsDir = path.join(__dirname, '..', '..', 'src', 'scripts');
  const mgr = new ScriptManager(scriptsDir);
  const HELPERS = ['ensure_project_open', 'select_application', 'find_object_by_path'];

  it('set_nvl_sender prepares with every parameter interpolated', () => {
    const script = mgr.prepareScriptWithHelpers('set_nvl_sender', {
      PROJECT_FILE_PATH: 'C:\\test.project', APPLICATION_PATH: '"Master"',
      GVL_PATH: '"Master/Plc Logic/Application/GVL_NvlTx"', LIST_IDENTIFIER: '1', TASK_NAME: '"MainTask"',
      PORT: '1202', BROADCAST_ADDRESS: '"10.0.0.255"', INTERVAL: '"T#100ms"', MIN_GAP: '"T#20ms"',
      CYCLIC: 'True', ON_CHANGE: 'False', PACK_VARIABLES: 'True', CHECKSUM: 'False', ACKNOWLEDGE: 'False',
    }, HELPERS);
    expect(script).toContain('GVL_PATH = "Master/Plc Logic/Application/GVL_NvlTx"');
    expect(script).toContain('LIST_IDENTIFIER = 1');
    expect(script).toContain('CreateNetVarProperties');
    expect(script).toContain('nvp.ListIdentifier = str(LIST_IDENTIFIER)');
    expect(script).toContain('SetParameterValue');
    expect(script).toContain('om.SetObject(mo, True, None)');
    expect(script).toContain('SystemInstances.ObjectMgr');
    expect(script).toContain('def find_object_by_path_robust');
    expect(script).toContain('### NVL_SENDER_START ###');
    expect(script).toContain('SCRIPT_SUCCESS');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('create_nvl_receiver prepares and binds the sender guid', () => {
    const script = mgr.prepareScriptWithHelpers('create_nvl_receiver', {
      PROJECT_FILE_PATH: 'C:\\test.project', APPLICATION_PATH: '""',
      RECEIVER_NAME: '"NVL_Rx_Node1"', PARENT_PATH: '"Master/Plc Logic/Application"',
      SENDER_GVL_PATH: '"Slave/Plc Logic/Application/GVL_NvlTx"', TASK_NAME: '"MainTask"',
      LIST_IDENTIFIER: '11', PORT: '1202', BROADCAST_ADDRESS: '"255.255.255.255"',
    }, HELPERS);
    expect(script).toContain('RECEIVER_NAME = "NVL_Rx_Node1"');
    expect(script).toContain('recv.SenderGVLGuid = sender_guid');
    expect(script).toContain('recv.TaskName = TASK_NAME');
    expect(script).toContain('ObjectFactoryManager');
    expect(script).toContain('### NVL_RECEIVER_START ###');
    expect(script).toContain('SCRIPT_SUCCESS');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('server.ts registers both tools with applicationPath', () => {
    const server = fs.readFileSync(path.join(__dirname, '..', '..', 'src', 'server.ts'), 'utf-8').replace(/\r\n/g, '\n');
    for (const tool of ['set_nvl_sender', 'create_nvl_receiver']) {
      const i = server.indexOf(`\n  s.tool(\n    '${tool}',`);
      expect(i, `${tool} registered`).toBeGreaterThan(-1);
      const j = server.indexOf('\n  s.tool(\n', i + 20);
      const block = server.substring(i, j);
      expect(block).toContain('applicationPath: z.string().optional().describe(APP_PATH_DESC)');
      expect(block).toContain("['ensure_project_open', 'select_application', 'find_object_by_path']");
    }
  });

  it('NVL scripts are ASCII-only (IronPython 2.7 constraint)', () => {
    for (const name of ['set_nvl_sender', 'create_nvl_receiver']) {
      const src = fs.readFileSync(path.join(scriptsDir, `${name}.py`), 'utf-8');
      // eslint-disable-next-line no-control-regex
      expect(/^[\x00-\x7F]*$/.test(src), `${name} non-ASCII`).toBe(true);
    }
  });
});
