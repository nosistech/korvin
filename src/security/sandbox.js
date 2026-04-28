const { exec } = require('child_process');

const DOCKER_IMAGE = 'alpine:latest';
const MEMORY_LIMIT = '512m';
const TIMEOUT_SEC = 30;

function execInSandbox(command) {
  return new Promise((resolve, reject) => {
    const cmd = `docker run --rm --network none --memory=${MEMORY_LIMIT} --read-only ${DOCKER_IMAGE} sh -c ${JSON.stringify(command)}`;
    let timeoutId;
    const child = exec(cmd, { timeout: TIMEOUT_SEC * 1000 }, (error, stdout, stderr) => {
      clearTimeout(timeoutId);
      if (error) {
        if (error.killed) return reject(new Error(`Sandbox command timed out after ${TIMEOUT_SEC}s`));
        return resolve({ stdout: stdout.trim(), stderr: stderr.trim(), exitCode: error.code || 1 });
      }
      resolve({ stdout: stdout.trim(), stderr: stderr.trim(), exitCode: 0 });
    });
    timeoutId = setTimeout(() => { child.kill('SIGKILL'); reject(new Error(`Sandbox safety timeout after ${TIMEOUT_SEC}s`)); }, TIMEOUT_SEC * 1000 + 2000);
  });
}

function execInSandboxNetwork(command) {
  return new Promise((resolve, reject) => {
    const cmd = `docker run --rm --network bridge --memory=${MEMORY_LIMIT} ${DOCKER_IMAGE} sh -c ${JSON.stringify(command)}`;
    let timeoutId;
    const child = exec(cmd, { timeout: TIMEOUT_SEC * 1000 }, (error, stdout, stderr) => {
      clearTimeout(timeoutId);
      if (error && error.killed) return reject(new Error(`Sandbox network command timed out after ${TIMEOUT_SEC}s`));
      resolve({
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        exitCode: error ? (error.code || 1) : 0
      });
    });
    timeoutId = setTimeout(() => { child.kill('SIGKILL'); reject(new Error(`Network sandbox safety timeout`)); }, TIMEOUT_SEC * 1000 + 2000);
  });
}

module.exports = { execInSandbox, execInSandboxNetwork };
