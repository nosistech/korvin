// sandbox.js — execute commands in an isolated Docker container

const { exec } = require('child_process');

const DOCKER_IMAGE = 'alpine:latest';
const MEMORY_LIMIT = '512m';
const TIMEOUT_SEC = 30;

/**
 * Run a shell command inside a disposable Docker container.
 * @param {string} command - the shell command to execute
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
function execInSandbox(command) {
  return new Promise((resolve, reject) => {
    const cmd = `docker run --rm --network none --memory=${MEMORY_LIMIT} --read-only ${DOCKER_IMAGE} sh -c ${JSON.stringify(command)}`;
    let timeoutId;

    const child = exec(cmd, { timeout: TIMEOUT_SEC * 1000 }, (error, stdout, stderr) => {
      clearTimeout(timeoutId);
      if (error) {
        // Docker run error or timeout
        if (error.killed) {
          return reject(new Error(`Sandbox command timed out after ${TIMEOUT_SEC}s`));
        }
        // Non-zero exit code is still a result, but treat as failure
        return resolve({
          stdout: stdout.trim(),
          stderr: stderr.trim(),
          exitCode: error.code || 1
        });
      }
      resolve({
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        exitCode: 0
      });
    });

    // Extra safety timeout
    timeoutId = setTimeout(() => {
      child.kill('SIGKILL');
      reject(new Error(`Sandbox safety timeout after ${TIMEOUT_SEC}s`));
    }, TIMEOUT_SEC * 1000 + 2000);
  });
}

module.exports = { execInSandbox };

// Quick test
if (require.main === module) {
  (async () => {
    try {
      console.log('Testing sandbox...');
      const result = await execInSandbox('echo "Hello from inside the sandbox!"');
      console.log('stdout:', result.stdout);
      console.log('exitCode:', result.exitCode);
    } catch (err) {
      console.error('Sandbox test failed:', err.message);
    }
  })();
}
