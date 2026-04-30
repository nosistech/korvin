const LITELLM_URL = 'http://localhost:4000/v1/chat/completions';
const ACTIVE_MODEL_PATH = '/home/korvin/korvin/data/active_model.txt';
function getActiveModel() {
  try {
    return fs.readFileSync(ACTIVE_MODEL_PATH, 'utf8').trim();
  } catch (_) {
    return 'deepseek-v4-pro';
  }
}
const API_KEY = process.env.LITELLM_MASTER_KEY;
if (!API_KEY) throw new Error('LITELLM_MASTER_KEY not set in /etc/korvin.env');
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
  let response;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      response = await fetch(LITELLM_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
        body: JSON.stringify({ model: getActiveModel(), messages, temperature: 0.7, stream: false })
      });
      break;
    } catch (err) {
      if (attempt === 0 && err.code === 'ECONNREFUSED') {
        await new Promise(r => setTimeout(r, 3000));
      } else {
        throw err;
      }
    }
  }
  if (!response.ok) throw new Error(`LiteLLM error: ${response.status} ${response.statusText}`);
  const data = await response.json();
  const reply = data.choices[0].message.content;
  saveMessage(chatId, 'user', safeMessage);
  saveMessage(chatId, 'assistant', reply);
  return reply;
}

module.exports = { sendMessage };
