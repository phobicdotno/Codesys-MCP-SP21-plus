import { describe, it, expect } from 'vitest';
import * as path from 'path';
import * as fs from 'fs';
import { ScriptManager } from '../../src/script-manager';

/**
 * Script-preparation tests for the four Sjobjorn-seed tool fixes
 * (2026-09-03). No CODESYS required.
 *
 *  1. ensure_project_open must never save the previously open project when
 *     switching (it once rewrote a template used only as an export source);
 *     a dirty prior primary is a hard refusal, not a silent save.
 *  2. mirror_export prunes stale .st files (deleted/renamed objects) and
 *     empty directories, but only signature-matched files and only after a
 *     clean walk.
 *  3. remove_pou_from_task verifies against a freshly re-walked task object,
 *     not the mutated ref (stale ref showed the entry gone while the project
 *     still had it).
 *  4. set_device_parameter can write array/struct parameters element-wise
 *     (elementIndex) or whole ('[v0, v1, ...]').
 */
describe('Script safety guards — Sjobjorn seed fixes', () => {
  const scriptsDir = path.join(__dirname, '..', '..', 'src', 'scripts');
  const mgr = new ScriptManager(scriptsDir);
  const P = { PROJECT_FILE_PATH: 'C:\\test.project' };

  it('ensure_project_open refuses to switch away from a dirty project and never saves it', () => {
    const helper = fs.readFileSync(path.join(scriptsDir, 'ensure_project_open.py'), 'utf-8');
    expect(helper).toContain('class DirtyProjectSwitchError');
    expect(helper).toContain('Refusing to switch projects');
    expect(helper).toContain('ensure_project_open never saves a project on its own');
    // The refusal must escape the broad retry-loop handler.
    expect(helper).toContain('except DirtyProjectSwitchError:');
    // The old silent primary_project.save() before close is gone.
    expect(helper).not.toContain('primary_project.save()');
    expect(helper).not.toContain('Saved prior primary');
  });

  it('mirror_export prunes stale export files and empty dirs, signature-guarded, skipped on walk errors', () => {
    const script = mgr.prepareScriptWithHelpers(
      'mirror_export', { ...P, MIRROR_ROOT: 'C:\\test-mirror' }, ['ensure_project_open']
    );
    expect(script).toContain('def prune_stale');
    // Only files carrying the export header are ever deleted.
    expect(script).toContain("EXPORT_SIGNATURE = u'(* === CODESYS export'");
    expect(script).toContain('first_line.startswith(EXPORT_SIGNATURE)');
    // A walk error means an unwritten live object; pruning must not run.
    expect(script).toContain('skipping stale-file pruning');
    expect(script).toContain('Stale pruned:');
    expect(script).toContain('SCRIPT_SUCCESS');
  });

  it('remove_pou_from_task verifies the removal on a freshly re-walked task object', () => {
    const script = mgr.prepareScriptWithHelpers(
      'remove_pou_from_task', { ...P, TASK_NAME: 'MainTask', POU_NAME: 'PLC_PRG' }, ['ensure_project_open']
    );
    expect(script).toContain('fresh_task = find_task(fresh_tc, TASK_NAME)');
    expect(script).toContain('for p in fresh_task.pous');
    expect(script).toContain("STILL in task");
    // The stale mutated ref must not be what the verification reads.
    expect(script).not.toMatch(/primary_project\.save\(\)[\s\S]*for p in task\.pous/);
  });

  it('set_device_parameter supports elementIndex and whole-array literals', () => {
    const script = mgr.prepareScriptWithHelpers(
      'set_device_parameter',
      { ...P, DEVICE_PATH: '', PARAM_NAME: '""', PARAM_ID: '7', NEW_VALUE: '"[1, 2, 3]"', GET_ONLY: 'False', ELEMENT_INDEX: '' },
      ['ensure_project_open', 'find_object_by_path', 'find_device_object']
    );
    expect(script).toContain('def _sub_elements');
    expect(script).toContain('def _parse_array_literal');
    expect(script).toContain("ELEMENT_INDEX = r\"\"");
    expect(script).toContain('Parameter array set');
    const single = mgr.prepareScriptWithHelpers(
      'set_device_parameter',
      { ...P, DEVICE_PATH: '', PARAM_NAME: '""', PARAM_ID: '7', NEW_VALUE: '"42"', GET_ONLY: 'False', ELEMENT_INDEX: '3' },
      ['ensure_project_open', 'find_object_by_path', 'find_device_object']
    );
    expect(single).toContain('ELEMENT_INDEX = r"3"');
    expect(single).toContain('Parameter element set');
  });

  it('changed scripts stay ASCII-only (IronPython 2.7 constraint)', () => {
    for (const name of ['ensure_project_open', 'mirror_export', 'remove_pou_from_task', 'set_device_parameter']) {
      const text = fs.readFileSync(path.join(scriptsDir, `${name}.py`), 'utf-8');
      expect(/^[\x00-\x7F]*$/.test(text), `${name}.py contains non-ASCII`).toBe(true);
    }
  });
});
