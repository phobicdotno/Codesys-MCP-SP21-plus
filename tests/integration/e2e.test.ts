import { describe, it, expect } from 'vitest';
import * as path from 'path';
import { ScriptManager } from '../../src/script-manager';

/**
 * Integration tests that verify the full script preparation pipeline.
 * These don't require CODESYS but verify the template system works end-to-end.
 */
describe('E2E Script Preparation', () => {
  const scriptsDir = path.join(__dirname, '..', '..', 'src', 'scripts');
  const mgr = new ScriptManager(scriptsDir);

  it('open_project script prepares correctly with helpers', () => {
    const script = mgr.prepareScriptWithHelpers(
      'open_project',
      { PROJECT_FILE_PATH: 'C:\\Projects\\Test.project' },
      ['ensure_project_open']
    );
    // Should contain ensure_project_open function
    expect(script).toContain('def ensure_project_open');
    // Should contain the actual open logic
    expect(script).toContain('Project Opened');
    // Path should appear as-is (no escaping) since templates use r"..." raw strings
    expect(script).toContain('C:\\Projects\\Test.project');
    // Should contain success marker
    expect(script).toContain('SCRIPT_SUCCESS');
  });

  it('create_pou script prepares with both helpers', () => {
    const script = mgr.prepareScriptWithHelpers(
      'create_pou',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        POU_NAME: 'MyProgram',
        POU_TYPE_STR: 'Program',
        IMPL_LANGUAGE_STR: 'ST',
        PARENT_PATH: 'Application',
      },
      ['ensure_project_open', 'find_object_by_path']
    );
    expect(script).toContain('def ensure_project_open');
    expect(script).toContain('def find_object_by_path_robust');
    expect(script).toContain('MyProgram');
    expect(script).toContain('POU_TYPE_STR = "Program"');
  });

  it('set_pou_code script handles pre-escaped code content', () => {
    // Simulate what server.ts does: manually escape code for triple-quoted strings
    const declCode = 'VAR\\n  x : INT;\\nEND_VAR';
    const implCode = 'x := 42;';
    const sanDecl = declCode.replace(/\\/g, '\\\\').replace(/"""/g, '\\"\\"\\"');
    const sanImpl = implCode.replace(/\\/g, '\\\\').replace(/"""/g, '\\"\\"\\"');

    const script = mgr.prepareScriptWithHelpers(
      'set_pou_code',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        POU_FULL_PATH: 'Application/MyPOU',
        DECLARATION_CONTENT: sanDecl,
        IMPLEMENTATION_CONTENT: sanImpl,
        SET_DECLARATION: 'True',
        SET_IMPLEMENTATION: 'True',
      },
      ['ensure_project_open', 'find_object_by_path']
    );
    expect(script).toContain('Application/MyPOU');
    expect(script).toContain('x := 42;');
    expect(script).toContain('SET_DECLARATION = True');
    expect(script).toContain('SET_IMPLEMENTATION = True');
  });

  it('set_pou_code with omitted declarationCode gates the replace() call', () => {
    // Regression: when caller omits declarationCode, the script must NOT
    // call decl_obj.replace('') -- doing so wipes the POU's
    // PROGRAM/VAR...END_VAR block (binary becomes UNKNOWN POU).
    // server.ts passes SET_DECLARATION='False' in that case.
    const script = mgr.prepareScriptWithHelpers(
      'set_pou_code',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        POU_FULL_PATH: 'Application/PLC_PRG',
        DECLARATION_CONTENT: '',
        IMPLEMENTATION_CONTENT: 'x := 1;',
        SET_DECLARATION: 'False',
        SET_IMPLEMENTATION: 'True',
      },
      ['ensure_project_open', 'find_object_by_path']
    );
    expect(script).toContain('SET_DECLARATION = False');
    expect(script).toContain('SET_IMPLEMENTATION = True');
    // The skip branch must be reachable
    expect(script).toContain('SET_DECLARATION=False');
    // No leftover {PLACEHOLDER} unsubstituted
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('add_library script gates save() on resolution and backs out unresolved placeholders', () => {
    // Regression: add_library used to call lm.add_library(name) (the
    // placeholder overload) and then immediately project.save(), even when
    // the placeholder could not be resolved. The next open then threw
    // "The placeholder library 'X' could not be resolved." and bricked the
    // project. The fixed script must:
    //   - pre-resolve via the IDE-level library_manager.find_library(name)
    //     and prefer the ManagedLib overload of lm.add_library
    //   - after add, walk lm.references to locate the new entry and check
    //     that it resolved (managed -> always; placeholder -> non-empty
    //     effective_resolution)
    //   - if not resolved, call lm.remove_library(name) and refuse to save
    const script = mgr.prepareScriptWithHelpers(
      'add_library',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        LIBRARY_NAME: 'Util',
        USE_DIRECT: '0',
        FORCE_DUP: '0',
        ALLOW_UNRESOLVED: '0',
      },
      ['ensure_project_open']
    );
    expect(script).toContain('LIBRARY_NAME = "Util"');
    // Pre-resolve via the IDE-level library_manager
    expect(script).toContain('library_manager');
    expect(script).toContain('find_library');
    // Managed-overload preference (when USE_DIRECT=1 or add_placeholder unavailable)
    expect(script).toContain('add_library(resolved_lib)');
    // Default-to-placeholder branch added per Bug 4
    expect(script).toContain('add_placeholder');
    // Dedup pre-check added per Bug 4
    expect(script).toContain('FORCE_DUP');
    expect(script).toContain('Library Already Present');
    // Post-add resolution gate
    expect(script).toContain('effective_resolution');
    expect(script).toContain('is_placeholder');
    expect(script).toContain('_is_resolved');
    // Back-out path on failure
    expect(script).toContain('remove_library');
    // The actionable error string the user will see
    expect(script).toContain('not installed in the CODESYS library repository');
    // save() in the body of add_library proper must come AFTER the
    // resolution gate. (The ensure_project_open helper, prepended above,
    // also calls primary_project.save() once -- so use lastIndexOf to
    // pick up the add_library save call.)
    const saveIdx = script.lastIndexOf('primary_project.save()');
    const gateIdx = script.indexOf('_is_resolved(new_ref)');
    expect(gateIdx).toBeGreaterThan(0);
    expect(saveIdx).toBeGreaterThan(gateIdx);
    // No unsubstituted placeholders
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('remove_library script renders without leftover placeholders and contains required markers', () => {
    const script = mgr.prepareScriptWithHelpers(
      'remove_library',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        LIBRARY_NAME: 'Standard',
        LIBRARY_FQN_OR_NAME: 'Standard, 3.5.17.0 (System)',
      },
      ['ensure_project_open']
    );
    // Placeholders must all be substituted
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
    // Substituted values must appear
    expect(script).toContain('LIBRARY_NAME = "Standard"');
    expect(script).toContain('LIBRARY_FQN_OR_NAME = "Standard, 3.5.17.0 (System)"');
    // Core SP22 API call
    expect(script).toContain('lm.remove_library' || 'remove_library');
    expect(script).toContain('remove_library');
    // references walk must be present (pre-check)
    expect(script).toContain('references');
    // Idempotent no-op marker
    expect(script).toContain('Library Not Present');
    // Success and error markers
    expect(script).toContain('SCRIPT_SUCCESS');
    expect(script).toContain('SCRIPT_ERROR');
  });

  it('check_status script has no placeholders after load', () => {
    const script = mgr.loadTemplate('check_status');
    // check_status has no {PLACEHOLDER} params
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
    expect(script).toContain('SCRIPT_SUCCESS');
  });

  it('compile_project script prepares with ensure_project_open', () => {
    const script = mgr.prepareScriptWithHelpers(
      'compile_project',
      { PROJECT_FILE_PATH: 'C:\\test.project' },
      ['ensure_project_open']
    );
    expect(script).toContain('def ensure_project_open');
    expect(script).toContain('build()');
  });

  it('rename_object script renders the references-update branch with UPDATE_REFERENCES=1', () => {
    // Bug 5: rename_object historically only updated the target's own
    // decl, not callers in other POUs. The fixed script must:
    //   - default to project-wide identifier rewrite via word-boundary regex
    //   - opt-out via UPDATE_REFERENCES=0
    //   - import re and walk text-bearing nodes
    const script = mgr.prepareScriptWithHelpers(
      'rename_object',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        OBJECT_PATH: 'Application/ST_Sample',
        NEW_NAME: 'ST_SampleRenamed',
        UPDATE_REFERENCES: '1',
      },
      ['ensure_project_open', 'find_object_by_path']
    );
    expect(script).toContain('def find_object_by_path_robust');
    expect(script).toContain('OBJECT_PATH = "Application/ST_Sample"');
    expect(script).toContain('NEW_NAME = "ST_SampleRenamed"');
    expect(script).toContain('UPDATE_REFERENCES = "1" == "1"');
    expect(script).toContain('import sys, scriptengine as script_engine, os, traceback, re');
    expect(script).toContain('re.escape(old_identifier)');
    expect(script).toContain('textual_declaration');
    expect(script).toContain('textual_implementation');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('rename_object script honours UPDATE_REFERENCES=0 opt-out', () => {
    const script = mgr.prepareScriptWithHelpers(
      'rename_object',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        OBJECT_PATH: 'Application/Foo',
        NEW_NAME: 'Bar',
        UPDATE_REFERENCES: '0',
      },
      ['ensure_project_open', 'find_object_by_path']
    );
    expect(script).toContain('UPDATE_REFERENCES = "0" == "1"');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('all scripts are loadable', () => {
    const scriptNames = [
      'check_status', 'compile_project', 'create_method', 'create_pou',
      'create_project', 'create_property', 'ensure_project_open',
      'find_object_by_path', 'get_pou_code', 'get_project_structure',
      'open_project', 'save_project', 'set_pou_code', 'watcher',
    ];
    for (const name of scriptNames) {
      expect(() => mgr.loadTemplate(name)).not.toThrow();
      const content = mgr.loadTemplate(name);
      expect(content.length).toBeGreaterThan(0);
    }
  });

  // ─── Symbol Configuration tools ──────────────────────────────────────
  // Each new tool: assert the rendered script substitutes every {PLACEHOLDER},
  // pulls in find_symbol_config_object helper, and emits SCRIPT_SUCCESS.

  const SYMCONF_HELPERS = ['ensure_project_open', 'find_symbol_config_object'];

  it('find_symbol_config script renders cleanly with helpers', () => {
    const script = mgr.prepareScriptWithHelpers(
      'find_symbol_config',
      { PROJECT_FILE_PATH: 'C:\\test.project' },
      SYMCONF_HELPERS
    );
    expect(script).toContain('def find_all_symbol_config_objects');
    expect(script).toContain('def symbol_config_path');
    expect(script).toContain('SYMBOL_CONFIG_FIND_START');
    expect(script).toContain('SCRIPT_SUCCESS');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('list_all_signatures honours COMPILE_FLAG=1 to force a build', () => {
    const script = mgr.prepareScriptWithHelpers(
      'list_all_signatures',
      { PROJECT_FILE_PATH: 'C:\\test.project', COMPILE_FLAG: '1' },
      SYMCONF_HELPERS
    );
    expect(script).toContain('COMPILE_FLAG = "1"');
    expect(script).toContain('get_all_signatures');
    expect(script).toContain('def ensure_symbol_config');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('list_all_datatypes honours COMPILE_FLAG=0 (cached)', () => {
    const script = mgr.prepareScriptWithHelpers(
      'list_all_datatypes',
      { PROJECT_FILE_PATH: 'C:\\test.project', COMPILE_FLAG: '0' },
      SYMCONF_HELPERS
    );
    expect(script).toContain('COMPILE_FLAG = "0"');
    expect(script).toContain('get_all_datatypes');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('list_configured_symbols renders both signature + datatype paths', () => {
    const script = mgr.prepareScriptWithHelpers(
      'list_configured_symbols',
      { PROJECT_FILE_PATH: 'C:\\test.project' },
      SYMCONF_HELPERS
    );
    expect(script).toContain('get_only_configured_signatures');
    expect(script).toContain('get_only_configured_datatypes');
    expect(script).toContain('configured_access');
    expect(script).toContain('maximal_access');
    expect(script).toContain('effective_access');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('get_symbol_config_settings reads every documented knob', () => {
    const script = mgr.prepareScriptWithHelpers(
      'get_symbol_config_settings',
      { PROJECT_FILE_PATH: 'C:\\test.project' },
      SYMCONF_HELPERS
    );
    expect(script).toContain('content_feature_flags');
    expect(script).toContain('symbol_attribute_filter_type');
    expect(script).toContain('symbol_comment_filter_type');
    expect(script).toContain('enable_direct_io_access');
    expect(script).toContain('client_side_layout_calculator');
    expect(script).toContain('check_effective_direct_io_access');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('create_symbol_config emits the application.create_symbol_config call + idempotency check', () => {
    const script = mgr.prepareScriptWithHelpers(
      'create_symbol_config',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        APPLICATION_PATH: 'Application',
        EXPORT_COMMENTS_TO_XML: '1',
        SUPPORT_OPC_UA: '1',
        LAYOUT_CALCULATOR: 'compatibility',
      },
      [...SYMCONF_HELPERS, 'find_object_by_path']
    );
    expect(script).toContain('application.create_symbol_config');
    expect(script).toContain('Symbol Configuration already exists');
    expect(script).toContain('def find_object_by_path_robust');
    expect(script).toContain('LAYOUT_CALCULATOR = "compatibility"');
    expect(script).toContain('APPLICATION_PATH = "Application"');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('set_symbol_config_settings only applies fields whose APPLY_* flag is 1', () => {
    const script = mgr.prepareScriptWithHelpers(
      'set_symbol_config_settings',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        APPLY_CONTENT_FLAGS: '1',
        CONTENT_FLAGS_INT: '7',
        APPLY_ATTR_FILTER_TYPE: '0',
        ATTR_FILTER_TYPE: 'None',
        APPLY_ATTR_FILTER_DATA: '0',
        ATTR_FILTER_DATA: '',
        APPLY_COMMENT_FILTER_TYPE: '0',
        COMMENT_FILTER_TYPE: 'None',
        APPLY_DIRECT_IO: '0',
        DIRECT_IO: '0',
        APPLY_LAYOUT: '0',
        LAYOUT_CALCULATOR: 'compatibility',
      },
      SYMCONF_HELPERS
    );
    expect(script).toContain('APPLY_CONTENT_FLAGS = "1" == \'1\'');
    expect(script).toContain('CONTENT_FLAGS_INT = "7"');
    expect(script).toContain('APPLY_ATTR_FILTER_TYPE = "0" == \'1\'');
    expect(script).toContain('Refusing to enable direct I/O access');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('set_symbol_access emits the configured_access setter and access enum probe', () => {
    const script = mgr.prepareScriptWithHelpers(
      'set_symbol_access',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        SIGNATURE_FQN: 'Application.PLC_PRG',
        VARIABLE_NAME: 'nCounter',
        ACCESS: 'ReadWrite',
        LIBRARY_ID: '',
        ENSURE_CONFIGURED: '1',
      },
      SYMCONF_HELPERS
    );
    expect(script).toContain('SIGNATURE_FQN = r"Application.PLC_PRG"');
    expect(script).toContain('VARIABLE_NAME = r"nCounter"');
    expect(script).toContain('ACCESS = "ReadWrite"');
    expect(script).toContain('configured_access = requested_access');
    expect(script).toContain('SymbolAccess');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('set_signature_access_bulk walks every variable in the signature', () => {
    const script = mgr.prepareScriptWithHelpers(
      'set_signature_access_bulk',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        SIGNATURE_FQN: 'Application.PLC_PRG',
        ACCESS: 'ReadOnly',
        LIBRARY_ID: '',
      },
      SYMCONF_HELPERS
    );
    expect(script).toContain('for v in sig.variables');
    expect(script).toContain('changed.append');
    expect(script).toContain('skipped.append');
    expect(script).toContain('ACCESS = "ReadOnly"');
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('export_symbol_xsd writes bytes and refuses on missing parent dir', () => {
    const script = mgr.prepareScriptWithHelpers(
      'export_symbol_xsd',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        OUTPUT_FILE_PATH: 'C:\\out.xsd',
      },
      SYMCONF_HELPERS
    );
    expect(script).toContain('get_symbol_configuration_xsd');
    expect(script).toContain('Parent directory does not exist');
    expect(script).toContain('OUTPUT_FILE_PATH = r"C:\\out.xsd"');
    expect(script).toContain("open(OUTPUT_FILE_PATH, 'wb')");
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  // ───────── Regression tests for fixes landed 2026-04-29 ─────────

  it('set_symbol_access looks up mutation target via get_all_signatures, not the configured view', () => {
    // Fix from PR #7: get_only_configured_signatures returns a read-only
    // view; assigning to .configured_access on its variables raises
    // "The access of the variable can only be changed in the list of all
    // signatures/data types." The mutation lookup must hit
    // get_all_signatures FIRST (with both compile=False/True fallbacks);
    // the configured view is kept only as a tracking-only flag.
    const script = mgr.prepareScriptWithHelpers(
      'set_symbol_access',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        SIGNATURE_FQN: 'Application.PLC_PRG',
        VARIABLE_NAME: 'nCounter',
        ACCESS: 'None',
        LIBRARY_ID: '',
        ENSURE_CONFIGURED: '1',
      },
      SYMCONF_HELPERS
    );
    // get_all_signatures(False) and get_all_signatures(True) MUST be the
    // mutation lookup; they appear before any tracking probe.
    const allSigsFalseIdx = script.indexOf('get_all_signatures(False)');
    const allSigsTrueIdx = script.indexOf('get_all_signatures(True)');
    const trackingIdx = script.indexOf('found_in_configured');
    expect(allSigsFalseIdx).toBeGreaterThan(0);
    expect(allSigsTrueIdx).toBeGreaterThan(allSigsFalseIdx);
    // The tracking flag block (the configured-view probe) comes AFTER both
    // get_all_signatures lookups -- this is what makes the configured view
    // tracking-only, not the mutation target.
    expect(trackingIdx).toBeGreaterThan(allSigsTrueIdx);
  });

  it('set_symbol_access coerces int->SymbolAccess via type(maximal_access) before assigning', () => {
    // Fix from PR #9: when `from scriptengine import SymbolAccess` returns
    // a hollow class, _resolve_access falls back to a plain int and the
    // C# setter rejects every non-zero int with "Cannot convert numeric
    // value N to SymbolAccess. The value must be zero." The fix coerces
    // the int through the enum class extracted from var.maximal_access
    // BEFORE `var.configured_access = requested_access` runs.
    const script = mgr.prepareScriptWithHelpers(
      'set_symbol_access',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        SIGNATURE_FQN: 'Application.PLC_PRG',
        VARIABLE_NAME: 'nCounter',
        ACCESS: 'ReadOnly',
        LIBRARY_ID: '',
        ENSURE_CONFIGURED: '1',
      },
      SYMCONF_HELPERS
    );
    // Coercion block must reference type(max_access) and re-parse the int.
    expect(script).toContain('isinstance(requested_access, int)');
    expect(script).toContain('type(max_access)');
    expect(script).toContain('enum_cls(requested_access)');
    // The coercion must come BEFORE the actual assignment.
    const coerceIdx = script.indexOf('enum_cls(requested_access)');
    const assignIdx = script.indexOf('var.configured_access = requested_access');
    expect(coerceIdx).toBeGreaterThan(0);
    expect(assignIdx).toBeGreaterThan(coerceIdx);
  });

  it('set_signature_access_bulk coerces int->SymbolAccess lazily on the first variable', () => {
    // Same root cause as set_symbol_access; fix is per-loop because
    // requested_access is shared across all variables in a bulk run.
    // The coercion uses type(v.maximal_access) on the first iteration
    // and stays effective for the rest of the loop.
    const script = mgr.prepareScriptWithHelpers(
      'set_signature_access_bulk',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        SIGNATURE_FQN: 'Application.PLC_PRG',
        ACCESS: 'WriteOnly',
        LIBRARY_ID: '',
      },
      SYMCONF_HELPERS
    );
    expect(script).toContain('isinstance(requested_access, int)');
    expect(script).toContain('type(v.maximal_access)');
    expect(script).toContain('enum_cls(requested_access)');
    // Coercion must be inside the for-loop and BEFORE the assignment.
    const loopIdx = script.indexOf('for v in sig.variables');
    const coerceIdx = script.indexOf('enum_cls(requested_access)');
    const assignIdx = script.indexOf('v.configured_access = requested_access');
    expect(loopIdx).toBeGreaterThan(0);
    expect(coerceIdx).toBeGreaterThan(loopIdx);
    expect(assignIdx).toBeGreaterThan(coerceIdx);
  });

  it('create_project without deviceName preserves the no-swap path', () => {
    // Backwards-compat: omitting deviceName must produce a script that
    // does NOT touch device_repository / project.add / existing_device.
    const script = mgr.prepareScript('create_project', {
      PROJECT_FILE_PATH: 'C:\\test.project',
      TEMPLATE_PROJECT_PATH: 'C:\\template.project',
      DEVICE_NAME: '',
    });
    // Substituted empty deviceName.
    expect(script).toContain("DEVICE_NAME = r''");
    // The conditional swap branch is gated by `if DEVICE_NAME:` -- the
    // text of that branch is in the rendered script either way (it's a
    // template, not a generator), but the runtime check skips it.
    expect(script).toContain('if DEVICE_NAME:');
    // Substitution of the other args still works.
    expect(script).toContain("PROJECT_FILE_PATH = r'C:\\test.project'");
    expect(script).toContain("TEMPLATE_PROJECT_PATH = r'C:\\template.project'");
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('create_project deviceName swap renders prompt-suppression + update-first + close + cache delete', () => {
    // Combined regression for PRs #8/#10/#11/#12.
    const script = mgr.prepareScript('create_project', {
      PROJECT_FILE_PATH: 'C:\\test.project',
      TEMPLATE_PROJECT_PATH: 'C:\\template.project',
      DEVICE_NAME: 'CODESYS Control Win V3 x64',
    });
    expect(script).toContain("DEVICE_NAME = r'CODESYS Control Win V3 x64'");

    // Prompt suppression via the OBSOLETE-but-settable PromptHandling.NONE
    // (PR #12). Setting the read-only `script_prompt_handling` attribute
    // would silently fail.
    expect(script).toContain('PromptHandling');
    expect(script).toContain('system.prompt_handling = PromptHandling.NONE');
    // Int-literal fallback for environments where the enum import fails.
    expect(script).toContain('system.prompt_handling = 0');

    // Device lookup via the scriptengine module (PR #10).
    expect(script).toContain('script_engine.device_repository');
    expect(script).toContain('get_all_devices(name, None)');

    // Non-destructive default: try update() first (PR #11).
    const updateIdx = script.indexOf('existing_device.update(new_dev_id)');
    const removeIdx = script.indexOf('existing_device.remove()');
    const addIdx = script.indexOf('project.add(existing_name, new_dev_id)');
    expect(updateIdx).toBeGreaterThan(0);
    expect(removeIdx).toBeGreaterThan(updateIdx);
    expect(addIdx).toBeGreaterThan(removeIdx);
    // The destructive remove+add path is gated by `if not update_ok:`.
    expect(script).toContain('if not update_ok');

    // Post-swap cleanup (PR #12): close project, delete precompilecache.
    expect(script).toContain('project.close()');
    expect(script).toContain("'_project.precompilecache'");
    expect(script).toContain('os.remove(cache_path)');

    expect(script).not.toMatch(/\{[A-Z_]+\}/);
  });

  it('every symbol config script template loads without error', () => {
    const scriptNames = [
      'find_symbol_config', 'list_all_signatures', 'list_all_datatypes',
      'list_configured_symbols', 'get_symbol_config_settings',
      'create_symbol_config', 'set_symbol_config_settings',
      'set_symbol_access', 'set_signature_access_bulk', 'export_symbol_xsd',
      'find_symbol_config_object',
    ];
    for (const name of scriptNames) {
      expect(() => mgr.loadTemplate(name)).not.toThrow();
      const content = mgr.loadTemplate(name);
      expect(content.length).toBeGreaterThan(0);
    }
  });
});
