const LITELLM_URL = 'http://localhost:4000/v1/chat/completions';
const MODEL = 'deepseek-v4-pro';
const API_KEY = 'nosistech-proxy-2026';
const { sanitize: defendSanitize } = require('../security/defender');
const { sanitize: inputSanitize } = require('../middleware/sanitizer');
const { execSync } = require('child_process');
const fs = require('fs');

const SYSTEM_PROMPT = `You are Korvin, a self-hosted AI agent framework built by Carlos Paredes at NosisTech LLC. You are voice-first, security-native, and privacy-focused. You help users with research, document drafting, inbox management, and security monitoring. Always respond in English regardless of the language the user speaks in. Be concise, direct, and professional. Never include system warnings or technical notices in your replies.`;

function getHistory(chatId) {
  try {
    const result = execSync(
      `cd /home/korvin/korvin && venv/bin/python3 -c "import sys; sys.path.insert(0, 'src/hermes'); from memory import get_history; import json; print(json.dumps(get_history('${chatId}', 10)))"`,
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    ).trim();
    return JSON.parse(result);
  } catch (e) {
    return [];
  }
}

function saveMessage(chatId, role, content) {
  try {
    const textFile = '/tmp/korvin_mem_text.txt';
    fs.writeFileSync(textFile, content, 'utf8');
    execSync(
      `cd /home/korvin/korvin && venv/bin/python3 -c "import sys; sys.path.insert(0, 'src/hermes'); from memory import save; text = open('/tmp/korvin_mem_text.txt').read(); save('${chatId}', '${role}', text)"`,
      { stdio: ['pipe', 'pipe', 'pipe'] }
    );
    fs.unlinkSync(textFile);
  } catch (e) {
    console.error('Memory save error:', e.message);
  }
}

async function sendMessage(userMessage, chatId = 'default') {
  const check = inputSanitize(userMessage);
  if (!check.safe) throw new Error(`Input blocked: ${check.reason}`);
  const safeMessage = defendSanitize(check.value);
  const history = getHistory(chatId);
  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
    ...history,
    { role: 'user', content: safeMessage }
  ];
  const response = await fetch(LITELLM_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
    body: JSON.stringify({ model: MODEL, messages, temperature: 0.7, stream: false })
  });
  if (!response.ok) throw new Error(`LiteLLM error: ${response.status} ${response.statusText}`);
  const data = await response.json();
  const reply = data.choices[0].message.content;
  saveMessage(chatId, 'user', safeMessage);
  saveMessage(chatId, 'assistant', reply);
  return reply;
}

module.exports = { sendMessage };
