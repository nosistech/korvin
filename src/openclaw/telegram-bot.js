const TelegramBot = require('node-telegram-bot-api');
const { execSync } = require('child_process');
const { sendMessage } = require('./gateway');
const fs = require('fs');
const path = require('path');
const https = require('https');

const BOT_TOKEN = require('../../config.json').telegramToken;
const bot = new TelegramBot(BOT_TOKEN, { polling: true });

const VOICE_DIR = '/tmp/korvin_voice';
if (!fs.existsSync(VOICE_DIR)) fs.mkdirSync(VOICE_DIR);

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
  const result = execSync(
    `cd /root/korvin && venv/bin/python3 -c "
import warnings, whisper
warnings.filterwarnings('ignore')
m = whisper.load_model('base')
r = m.transcribe('${audioPath}', fp16=False)
print(r['text'].strip())
"`,
    { encoding: 'utf8', stderr: 'pipe' }
  ).trim();
  return result;
}

function generateSpeech(text, outputPath) {
  const textFile = '/tmp/korvin_tts_input.txt';
  fs.writeFileSync(textFile, text, 'utf8');
  execSync(
    `cd /root/korvin && venv/bin/python3 -c "
import warnings, sys
warnings.filterwarnings('ignore')
sys.path.insert(0, 'src/voice')
from voice import generate_speech
text = open('/tmp/korvin_tts_input.txt').read()
generate_speech(text, '${outputPath}')
"`,
    { encoding: 'utf8' }
  );
  return outputPath;
}

function cleanReply(text) {
  return text
    .split('\n')
    .filter(line => !line.includes('repo_id') && !line.includes('WARNING') && !line.includes('UserWarning'))
    .join('\n')
    .trim();
}

bot.on('message', async (msg) => {
  const chatId = msg.chat.id;
  if (msg.text && !msg.voice) {
    try {
      const raw = await sendMessage(msg.text, String(msg.chat.id));
      const reply = cleanReply(raw);
      await bot.sendMessage(chatId, reply);
    } catch (err) {
      await bot.sendMessage(chatId, 'Error: ' + err.message);
    }
  }
});

bot.on('voice', async (msg) => {
  const chatId = msg.chat.id;
  console.log('Voice message received (file_id:', msg.voice.file_id + ')');
  try {
    const fileInfo = await bot.getFile(msg.voice.file_id);
    const fileUrl = `https://api.telegram.org/file/bot${BOT_TOKEN}/${fileInfo.file_path}`;
    const oggPath = path.join(VOICE_DIR, `${msg.voice.file_id}.ogg`);
    const wavPath = path.join(VOICE_DIR, `${msg.voice.file_id}.wav`);
    const replyWav = '/tmp/voice_reply.wav';

    await downloadFile(fileUrl, oggPath);
    execSync(`ffmpeg -y -i ${oggPath} ${wavPath} 2>/dev/null`);

    const transcript = transcribe(wavPath);
    console.log('Transcription:', transcript);

    const raw = await sendMessage(transcript, String(msg.chat.id));
    const reply = cleanReply(raw);
    console.log('AI reply:', reply);

    generateSpeech(reply, replyWav);
    await bot.sendVoice(chatId, replyWav);

    fs.unlinkSync(oggPath);
    fs.unlinkSync(wavPath);
  } catch (err) {
    console.error('Voice error:', err.message);
    await bot.sendMessage(chatId, 'Voice processing error: ' + err.message);
  }
});

console.log('Korvin Telegram bot started (voice ready). Send a text or voice message...');
