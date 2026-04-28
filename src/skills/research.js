const { execInSandboxNetwork } = require('../security/sandbox');
const { sanitize } = require('../security/defender');

async function researchTopic(topic) {
  const q = encodeURIComponent(topic);
  const cmd = `apk add -q lynx 2>/dev/null; lynx -dump "https://lite.duckduckgo.com/lite?q=${q}" | head -n 200`;
  const r = await execInSandboxNetwork(cmd);
  if (r.exitCode !== 0) throw new Error(r.stderr || 'Sandbox error');
  return sanitize(r.stdout);
}

module.exports = { researchTopic };
