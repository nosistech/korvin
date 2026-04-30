// src/commands/scan.js
// /scan <target> — VirusTotal lookup or system audit
'use strict';

function registerScan(bot, deps) {
  const { confirmationGate, logActivity } = deps;

  bot.onText(/\/scan(?:\s+(.+))?/, async (msg, match) => {
    const chatId = String(msg.chat.id);
    const userId = String(msg.from.id);
    const target = match[1] ? match[1].trim() : 'full-system';

    try {
      await confirmationGate({
        action: 'scan',
        args: { target },
        chatId,
        userId,
        sendMessage: (cid, text) => bot.sendMessage(cid, text, { parse_mode: 'Markdown' }),
        executor: async () => {
          // System scan
          if (target === 'system' || target === 'full-system') {
            await bot.sendMessage(chatId, '🔍 *Running system audit with lynis…*', { parse_mode: 'Markdown' });
            try {
              const { execSync } = require('child_process');
              const output = execSync('lynis audit system --quick 2>/dev/null | tail -40', {
                encoding: 'utf8',
                timeout: 60000
              });
              await bot.sendMessage(chatId, `📋 *Lynis System Audit*\n\n\`\`\`${output.substring(0, 3500)}\`\`\``, { parse_mode: 'Markdown' });
            } catch (e) {
              await bot.sendMessage(chatId, `❌ Lynis failed: ${e.message}`);
            }
            return;
          }

          // VirusTotal lookup
          const API_KEY = process.env.VIRUSTOTAL_API_KEY;
          if (!API_KEY) {
            await bot.sendMessage(chatId, '❌ VirusTotal API key not configured.');
            return;
          }

          await bot.sendMessage(chatId, `🔍 *Querying VirusTotal for \`${target}\`…*`, { parse_mode: 'Markdown' });

          const url = `https://www.virustotal.com/api/v3/search?query=${encodeURIComponent(target)}`;
          const res = await fetch(url, {
            headers: { 'x-apikey': API_KEY, 'Accept': 'application/json' }
          });

          if (!res.ok) {
            await bot.sendMessage(chatId, `❌ VirusTotal API error: ${res.status}`);
            return;
          }

          const json = await res.json();
          const items = json.data || [];

          if (items.length === 0) {
            await bot.sendMessage(chatId, `⚪ No results found for "${target}".`);
            return;
          }

          const lines = [`📋 *VirusTotal results for \`${target}\`*`, ''];

          for (const item of items.slice(0, 3)) {
            const type = item.type || 'unknown';
            const stats = item.attributes?.last_analysis_stats || {};
            const total = Object.values(stats).reduce((a, b) => a + b, 0) || 1;
            const malicious = stats.malicious || 0;
            const suspicious = stats.suspicious || 0;
            const emoji = malicious > 0 ? '🔴' : suspicious > 0 ? '🟡' : '🟢';

            lines.push(`${emoji} *${type.toUpperCase()}*`);
            lines.push(`  • Detected: ${malicious} malicious, ${suspicious} suspicious / ${total} engines`);
            if (item.attributes?.meaningful_name) {
              lines.push(`  • Name: ${item.attributes.meaningful_name}`);
            }
            lines.push('');
          }

          await bot.sendMessage(chatId, lines.join('\n'), { parse_mode: 'Markdown' });

          if (logActivity) {
            try { logActivity('scan_completed', target, `${items.length} results`); } catch (_) {}
          }
        }
      });
    } catch (err) {
      await bot.sendMessage(msg.chat.id, `❌ Scan error: ${err.message}`);
    }
  });
}

module.exports = { registerScan };