import { describe, it, expect } from 'vitest';
import * as path from 'path';
import { ScriptManager } from '../../src/script-manager';

const SCRIPTS_DIR = path.join(__dirname, '..', '..', 'src', 'scripts');

// create_symbol_config is combined with the select_application helper, which
// expects APPLICATION_PATH as a ready Python literal. On 2026-10-02 the tool
// passed the raw path, so the helper line became
//   APPLICATION_PATH = PFC200_8210/Plc Logic/Application   (SyntaxError)
// and with no path at all `APPLICATION_PATH =` - the tool could not run.
describe('create_symbol_config APPLICATION_PATH', () => {
  const mgr = new ScriptManager(SCRIPTS_DIR);
  const literal = "'PFC200_8210/Plc Logic/Application'";

  it('every APPLICATION_PATH assignment is the same Python literal', () => {
    const script = mgr.prepareScriptWithHelpers(
      'create_symbol_config',
      {
        PROJECT_FILE_PATH: 'C:/x.project',
        APPLICATION_PATH: literal,
        EXPORT_COMMENTS_TO_XML: '1',
        SUPPORT_OPC_UA: '1',
        LAYOUT_CALCULATOR: 'compatibility',
      },
      ['ensure_project_open', 'select_application', 'find_symbol_config_object', 'find_object_by_path']
    );
    const assignments = script
      .split('\n')
      .filter((l) => /^APPLICATION_PATH\s*=/.test(l))
      .map((l) => l.replace(/^APPLICATION_PATH\s*=\s*/, '').trim());
    expect(assignments.length).toBeGreaterThan(0);
    for (const value of assignments) {
      expect(value).toBe(literal);
    }
  });
});
