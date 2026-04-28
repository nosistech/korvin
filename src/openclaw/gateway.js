const LITELLM_URL = 'http://localhost:4000/v1/chat/completions';
const MODEL = 'deepseek-v4-pro';
const API_KEY = 'nosistech-proxy-2026';
const { sanitize } = require('../security/defender');

const SYSTEM_PROMPT = "You are Korvin, a self-hosted AI agent framework built by Carlos Paredes at NosisTech LLC. You are voice-first, security-native, and privacy-focused. You help users with research, document drafting, inbox management, and security monitoring. Always respond in the same language the user writes in. Be concise, direct, and professional.";

async function sendMessage(userMessage) {
  // Sanitize the user message before anything else
  const safeMessage = sanitize(userMessage);

  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: safeMessage }
  ];

  const response = await fetch(LITELLM_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${API_KEY}`
    },
    body: JSON.stringify({ model: MODEL, messages, temperature: 0.7 })
  });

  if (!response.ok) throw new Error(`LiteLLM error: ${response.status} ${response.statusText}`);
  const data = await response.json();
  return data.choices[0].message.content;
}

module.exports = { sendMessage };

// Quick standalone test
if (require.main === module) {
  (async () => {
    try {
      const reply = await sendMessage('Hello from Korvin!');
      console.log('AI response:', reply);
    } catch (err) {
      console.error('Test failed:', err.message);
    }
  })();
}
