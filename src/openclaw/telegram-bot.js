// src/openclaw/telegram-bot.js
// Korvin AI Security Agent — Phase B

'use strict';

const TelegramBot = require('node-telegram-bot-api');
const { exec, execSync } = require('child_process');
const { sendMessage } = require('./gateway');
const { researchTopic } = require('../skills/research');
const fs = require('fs');
const path = require('path');
const https = require('https');
const os = require('os');

// ── Middleware ────────────────────────────────────────────────────────────────
const { sanitizeInput } = require('../middleware/sanitizer');
const { confirmationGate, confirmAction, cancelAction, listPending } = require('../middleware/confirmation-gate');
const { defend } = require('../security/defender');

// ── Skills ────────────────────────────────────────────────────────────────────
const { logActivity, getLogSummary } = require('../skills/activity-log');

// ── Commands (Phase B) ────────────────────────────────────────────────────────
const { registerPatch } = require('../commands/patch');
const { registerScan } = require('../commands/scan');
const { registerCompliance } = require('../commands/compliance');
const { registerIncident } = require('../commands/incident');

// ── Dashboard (Phase B) ───────────────────────────────────────────────────────
const { startDashboard } = require('../dashboard-api/server');

// ── Bot init ──────────────────────────────────────────────────────────────────
const BOT_TOKEN = require('../../config.json').telegramToken;
const bot = new TelegramBot(BOT_TOKEN, { polling: true });

const VOICE_DIR = '/tmp/korvin_voice';
if (!fs.existsSync(VOICE_DIR)) fs.mkdirSync(VOICE_DIR);

// ── Helpers ───────────────────────────────────────────────────────────────────

function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https.get(url, res => {
      res.pipe(file);
      file.on('finish', () => { file.close(); resolve(dest); });
    }).on('error', reject);
  });
}

function transcribe(audioPath) {
  return execSync(
    `cd /home/korvin/korvin && venv/bin/python3 -c "
import warnings, whisper
warnings.filterwarnings('ignore')
m = whisper.load_model('base')
r = m.transcribe('${audioPath}', fp16=False)
print(r['text'].strip())
"`,
    { encoding: 'utf8', stderr: 'pipe' }
  ).trim();
}

function generateSpeech(text, outputPath) {
  return new Promise((resolve, reject) => {
    const textFile = '/tmp/korvin_tts_input.txt';
    const ttsText = text.replace(/\*\*(.*?)\*\*/g, '$1').replace(/\*(.*?)\*/g, '$1').replace(/`(.*?)`/g, '$1');
    fs.writeFileSync(textFile, ttsText, 'utf8');
    exec(
      `cd /home/korvin/korvin && venv/bin/python3 -c "
import warnings, sys
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src/voice')
from voice import generate_speech
text = open('/tmp/korvin_tts_input.txt').read()
generate_speech(text, '${outputPath}')
"`,
      (err) => err ? reject(err) : resolve(outputPath)
    );
  });
}

function cleanReply(text) {
  return text
    .split('\n')
    .filter(l => !l.includes('repo_id') && !l.includes('WARNING') && !l.includes('UserWarning'))
    .join('\n')
    .trim();
}

function cleanup(...files) {
  for (const f of files) {
    try { if (fs.existsSync(f)) fs.unlinkSync(f); } catch (_) {}
  }
}

// ── Research ──────────────────────────────────────────────────────────────────

async function getResearchSummary(topic) {
  const rawData = await researchTopic(topic);
  const prompt = `You are Korvin. Summarise the following search results for "${topic}". Give a concise report with key points. Only use information from the search results.\n\nSEARCH RESULTS:\n${rawData}`;
  const summary = await sendMessage(prompt);
  try { logActivity('research', topic, summary); } catch (_) {}
  return summary;
}

// ── System Status ─────────────────────────────────────────────────────────────

function getSystemStatus() {
  try {
    const sys = JSON.parse(execSync('curl -s --max-time 2 http://localhost:3000/api/system').toString());
    return `🟢 *Korvin Online*\n` +
      `🧠 Model: deepseek-v4-pro\n` +
      `💾 Disk: ${sys.disk_used} / ${sys.disk_total} (${sys.disk_pct})\n` +
      `🧮 RAM: ${sys.mem_used_mb} MB / ${sys.mem_total_mb} MB (${sys.mem_pct}%)\n` +
      `📊 CPU Load: ${sys.load_1m} / ${sys.load_5m} / ${sys.load_15m}\n` +
      `⏱ Uptime: ${sys.uptime_hours}h`;
  } catch (_) {
    const total = os.totalmem();
    const free = os.freemem();
    const used = total - free;
    const load = os.loadavg();
    let disk = 'N/A';
    try {
      disk = execSync("df -h / | tail -1 | awk '{print $3\"/\"$2\" (\"$5\")\"}'" ).toString().trim();
    } catch (_) {}
    return `🟡 *Korvin Online* _(dashboard offline)_\n` +
      `🧮 RAM: ${(used/1024/1024).toFixed(0)} MB / ${(total/1024/1024).toFixed(0)} MB (${((used/total)*100).toFixed(1)}%)\n` +
      `💾 Disk: ${disk}\n` +
      `📊 CPU Load: ${load[0].toFixed(2)} / ${load[1].toFixed(2)} / ${load[2].toFixed(2)}\n` +
      `⏱ Uptime: ${(os.uptime()/3600).toFixed(1)}h`;
  }
}

// ── Command Handlers ──────────────────────────────────────────────────────────

bot.onText(/\/start|\/help/, async (msg) => {
  await bot.sendMessage(msg.chat.id,
    `🛡 *Korvin — AI Security Agent*\n\n` +
    `*Commands:*\n` +
    `\`/status\` — VPS health report\n` +
    `\`/scan [target]\` — Security scan (HIGH risk)\n` +
    `\`/patch <target>\` — Apply patch (HIGH risk)\n` +
    `\`/compliance <framework>\` — Compliance audit (MEDIUM risk)\n` +
    `\`/incident <severity> <description>\` — Log incident (MEDIUM risk)\n` +
    `\`/log\` — Recent activity\n` +
    `\`/pending\` — Pending confirmations\n` +
    `\`/help\` — this menu\n\n` +
    `*Skills:*\n` +
    `• Type or say \`Research <topic>\` — web research + voice summary\n` +
    `• Send any voice message — Korvin responds in voice\n` +
    `• Send any text — Korvin replies\n`,
    { parse_mode: 'Markdown' }
  );
});

bot.onText(/\/status/, async (msg) => {
  const report = getSystemStatus();
  await bot.sendMessage(msg.chat.id, report, { parse_mode: 'Markdown' });
});

bot.onText(/\/log/, async (msg) => {
  const summary = getLogSummary(10);
  await bot.sendMessage(msg.chat.id, `📋 *Recent Korvin Activity*\n\n${summary}`, { parse_mode: 'Markdown' });
});

// ── Confirmation Gate Handlers ────────────────────────────────────────────────

bot.onText(/\/confirm (.+)/, (msg, match) => {
  const result = confirmAction(match[1].trim(), String(msg.from.id));
  bot.sendMessage(msg.chat.id, result.message);
});

bot.onText(/\/cancel (.+)/, (msg, match) => {
  const result = cancelAction(match[1].trim(), String(msg.from.id));
  bot.sendMessage(msg.chat.id, result.message);
});

bot.onText(/\/pending/, (msg) => {
  const pending = listPending(String(msg.chat.id));
  if (pending.length === 0) return bot.sendMessage(msg.chat.id, 'No pending confirmations.');
  const lines = pending.map(p => p.pendingId + ' — ' + p.action).join('\n');
  bot.sendMessage(msg.chat.id, 'Pending:\n' + lines);
});

// ── Phase B Commands ──────────────────────────────────────────────────────────
const commandDeps = { confirmationGate, logActivity };
registerPatch(bot, commandDeps);
registerScan(bot, commandDeps);
registerCompliance(bot, commandDeps);
registerIncident(bot, commandDeps);

// ── Text Handler ──────────────────────────────────────────────────────────────

bot.on('message', async (msg) => {
  const chatId = msg.chat.id;
  const text = msg.text;
  if (!text || msg.voice) return;
  if (text.startsWith('/')) return;

  const sanity = sanitizeInput(text);
  if (sanity.safe === false) {
    await bot.sendMessage(chatId, 'Input rejected: ' + sanity.reason);
    return;
  }

  if (sanity.value.toLowerCase().startsWith('research ')) {
    const topic = sanity.value.substring(9).trim();
    await bot.sendMessage(chatId, `🔍 Researching "${topic}" …`);
    try {
      const summary = await getResearchSummary(topic);
      await bot.sendMessage(chatId, summary, { parse_mode: 'Markdown' });
    } catch (err) {
      await bot.sendMessage(chatId, `Research error: ${err.message}`);
    }
    return;
  }

  try {
    const reply = cleanReply(await sendMessage(text, String(chatId)));
    await bot.sendMessage(chatId, reply, { parse_mode: 'Markdown' });
  } catch (err) {
    await bot.sendMessage(chatId, 'Error: ' + err.message);
  }
});

// ── Voice Handler ─────────────────────────────────────────────────────────────

bot.on('voice', async (msg) => {
  const chatId = msg.chat.id;
  const oggPath = path.join(VOICE_DIR, `${msg.voice.file_id}.ogg`);
  const wavPath = path.join(VOICE_DIR, `${msg.voice.file_id}.wav`);
  const replyWav = `/tmp/voice_reply_${Date.now()}.wav`;

  console.log('Voice received:', msg.voice.file_id);
  try {
    const fileInfo = await bot.getFile(msg.voice.file_id);
    const fileUrl = `https://api.telegram.org/file/bot${BOT_TOKEN}/${fileInfo.file_path}`;

    await downloadFile(fileUrl, oggPath);
    execSync(`ffmpeg -y -i ${oggPath} ${wavPath} 2>/dev/null`);

    const transcript = transcribe(wavPath);
    console.log('Transcript:', transcript);
    const voiceCheck = sanitizeInput(transcript);
    if (!voiceCheck.safe) { await bot.sendMessage(chatId, `❌ Voice input blocked: ${voiceCheck.reason}`); cleanup(oggPath, wavPath, replyWav); return; }

    if (transcript.toLowerCase().includes('research ')) {
      const idx = transcript.toLowerCase().indexOf('research ') + 9;
      const topic = transcript.substring(idx).trim();
      await bot.sendMessage(chatId, `🔍 Researching "${topic}" …`);
      try {
        const summary = await getResearchSummary(topic);
        await bot.sendMessage(chatId, summary, { parse_mode: 'Markdown' });
        await generateSpeech(summary, replyWav);
        await bot.sendVoice(chatId, replyWav);
      } catch (err) {
        await bot.sendMessage(chatId, `Research error: ${err.message}`);
      }
      cleanup(oggPath, wavPath, replyWav);
      return;
    }

    const reply = cleanReply(await sendMessage(transcript, String(chatId)));
    console.log('Reply:', reply);
    await generateSpeech(reply, replyWav);
    await bot.sendVoice(chatId, replyWav);

  } catch (err) {
    console.error('Voice error:', err.message);
    await bot.sendMessage(chatId, 'Voice error: ' + err.message);
  } finally {
    cleanup(oggPath, wavPath, replyWav);
  }
});

// ── Boot ──────────────────────────────────────────────────────────────────────

(async () => {
  await startDashboard();
  console.log('Korvin bot started. /help for commands.');
})();