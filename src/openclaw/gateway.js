// gateway.js — initial connection test to LiteLLM

const LITELLM_URL = 'http://localhost:4000/v1/chat/completions';
const MODEL = 'deepseek-v4-pro'; // your primary reasoning model
const API_KEY = 'nosistech-proxy-2026';

async function sendMessage(userMessage) {
  const response = await fetch(LITELLM_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${API_KEY}`
    },
    body: JSON.stringify({
      model: MODEL,
      messages: [{ role: 'user', content: userMessage }],
      temperature: 0.7
    })
  });

  if (!response.ok) {
    throw new Error(`LiteLLM error: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  return data.choices[0].message.content;
}

// quick test
(async () => {
  try {
    const reply = await sendMessage('Hello from Korvin!');
    console.log('AI response:', reply);
  } catch (err) {
    console.error('Test failed:', err.message);
  }
})();
