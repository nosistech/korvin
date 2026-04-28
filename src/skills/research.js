const { execInSandboxNetwork } = require('../security/sandbox');

async function researchTopic(topic) {
  const query = encodeURIComponent(topic);
  const cmd = `apk add -q lynx 2>/dev/null; lynx -dump "https://lite.duckduckgo.com/lite?q=${query}" | head -n 200`;
  const result = await execInSandboxNetwork(cmd);
  if (result.exitCode !== 0) throw new Error(result.stderr || 'Sandbox error');
  return result.stdout;
}

module.exports = { researchTopic };
