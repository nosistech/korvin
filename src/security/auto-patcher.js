// auto-patcher.js — sandboxed patch application and validation

const { execInSandbox } = require('./sandbox');
const fs = require('fs');
const path = require('path');

const LOG_PATH = path.join(__dirname, '..', '..', 'logs', 'patches.log');

function logPatch(entry) {
  const dir = path.dirname(LOG_PATH);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  const timestamp = new Date().toISOString();
  fs.appendFileSync(LOG_PATH, `${timestamp} — ${entry}\n`);
}

/**
 * Attempt to apply a patch inside a sandbox.
 * @param {string} patchCommand - shell command that applies the patch
 * @param {string} testCommand - shell command that tests the patched state
 * @returns {Promise<{success: boolean, log: string}>}
 */
async function applyPatch(patchCommand, testCommand) {
  logPatch(`Attempting patch: ${patchCommand}`);
  try {
    // 1. Apply the patch in a sandbox (disposable container)
    const applyResult = await execInSandbox(patchCommand);
    if (applyResult.exitCode !== 0) {
      const msg = `Patch application failed (exit ${applyResult.exitCode}): ${applyResult.stderr || applyResult.stdout}`;
      logPatch(msg);
      return { success: false, log: msg };
    }

    // 2. Run the test command in a fresh sandbox
    const testResult = await execInSandbox(testCommand);
    if (testResult.exitCode !== 0) {
      const msg = `Tests failed after patch (exit ${testResult.exitCode}): ${testResult.stderr || testResult.stdout}`;
      logPatch(msg);
      // TODO: send Telegram alert
      return { success: false, log: msg };
    }

    // 3. All good — log success and (in future) apply to live system
    const msg = `Patch applied and tests passed. Ready for live deployment.`;
    logPatch(msg);
    return { success: true, log: msg };
  } catch (err) {
    const msg = `Sandbox error during patching: ${err.message}`;
    logPatch(msg);
    return { success: false, log: msg };
  }
}

module.exports = { applyPatch };

// Quick test
if (require.main === module) {
  (async () => {
    console.log('Running auto-patcher smoke test...\n');

    // Test 1: patch that succeeds and tests pass
    console.log('Test 1: simple echo patch');
    const r1 = await applyPatch('echo "patch applied"', 'echo "test ok"');
    console.log(r1.log);

    console.log('\nTest 2: patch that breaks the test');
    const r2 = await applyPatch('exit 0', 'exit 1');
    console.log(r2.log);

    console.log('\nSmoke test complete.');
  })();
}
