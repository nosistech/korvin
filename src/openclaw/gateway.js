const fs = require('fs');
const LITELLM_URL = 'http://localhost:4000/v1/chat/completions';
const ACTIVE_MODEL_PATH = '/home/korvin/korvin/data/active_model.txt';
const TOKEN_WARNING_PATH = '/home/korvin/korvin/data/token_warning_threshold.txt';
const CHAT_TIMEOUT_PATH = '/home/korvin/korvin/data/chat_timeout.txt';

function getActiveModel() {
  try {
    return fs.readFileSync(ACTIVE_MODEL_PATH, 'utf8').trim();
  } catch (_) {
    return 'deepseek-v4-pro';
  }
}

function readTokenWarningThreshold() {
  try {
    return parseInt(fs.readFileSync(TOKEN_WARNING_PATH, 'utf8').trim(), 10) || 5000;
  } catch (_) {
    return 5000;
  }
}

function readChatTimeout() {
  try {
    const val = parseInt(fs.readFileSync(CHAT_TIMEOUT_PATH, 'utf8').trim(), 10);
    return val >= 10 ? val : 180;
  } catch (_) {
    return 180;
  }
}

const API_KEY = process.env.LITELLM_MASTER_KEY;
if (!API_KEY) throw new Error('LITELLM_MASTER_KEY not set in /etc/korvin.env');

const { sanitize: defendSanitize } = require('../security/defender');
const { sanitize: inputSanitize } = require('../middleware/sanitizer');
const { execSync } = require('child_process');
function loadSystemPrompt() {
  const base = '/home/korvin/korvin';
  const local = base + '/KORVIN.local.md';
  const generic = base + '/KORVIN.md';
  try {
    if (fs.existsSync(local)) return fs.readFileSync(local, 'utf8');
    if (fs.existsSync(generic)) return fs.readFileSync(generic, 'utf8');
  } catch (_) {}
  return 'You are Korvin, a self-hosted personal AI agent. You are helpful, conversational, and warm.';
}
const SYSTEM_PROMPT = loadSystemPrompt();
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

function trackTokenUsage(model, tokens) {
  try {
    const file = '/home/korvin/korvin/data/token_usage.json';
    let usage = {};
    if (fs.existsSync(file)) {
      usage = JSON.parse(fs.readFileSync(file, 'utf8'));
    }
    const today = new Date().toISOString().split('T')[0];
    if (!usage[today]) usage[today] = {};
    const day = usage[today];
    if (!day[model]) day[model] = { tokens: 0 };
    day[model].tokens += tokens;
    day.total_tokens = (day.total_tokens || 0) + tokens;
    fs.writeFileSync(file, JSON.stringify(usage));
  } catch(e) {
    // silently ignore tracking errors
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
    const controller = new AbortController();
    const timeoutMs = readChatTimeout() * 1000;
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      response = await fetch(LITELLM_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${API_KEY}` },
        body: JSON.stringify({ model: getActiveModel(), messages, temperature: 0.7, stream: false }),
        signal: controller.signal
      });
      clearTimeout(timer);
      break;
    } catch (err) {
      clearTimeout(timer);
      if (err.name === 'AbortError') {
        if (attempt === 0) {
          await new Promise(r => setTimeout(r, 3000));
        } else {
          throw new Error(`LiteLLM timed out after ${readChatTimeout()} seconds`);
        }
      } else if (attempt === 0 && err.code === 'ECONNREFUSED') {
        await new Promise(r => setTimeout(r, 3000));
      } else {
        throw err;
      }
    }
  }
  if (!response.ok) throw new Error(`LiteLLM error: ${response.status} ${response.statusText}`);
  const data = await response.json();
  const reply = data.choices[0].message.content;

  const used = (data.usage && data.usage.total_tokens) || 0;
  const threshold = readTokenWarningThreshold();
  const budgetWarning = used > threshold
    ? `\n\n_💰 This response used ${used.toLocaleString()} tokens (~$${((used / 1_000_000) * 0.87).toFixed(4)}). Use /brief to reduce costs._`
    : '';

  const usage = data.usage;
  if (usage && usage.total_tokens) {
    trackTokenUsage(getActiveModel(), usage.total_tokens);
  }
  saveMessage(chatId, 'user', safeMessage);
  saveMessage(chatId, 'assistant', reply);
  return reply + budgetWarning;
}

module.exports = { sendMessage };