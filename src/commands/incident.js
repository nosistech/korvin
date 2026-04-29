// src/commands/incident.js
// /incident command — MEDIUM risk, uses confirmationGate

'use strict';

const SEVERITIES = ['low', 'medium', 'high', 'critical'];

function registerIncident(bot, deps) {
  const { confirmationGate, logActivity } = deps;

  bot.onText(/\/incident(?:\s+(.+))?/, async (msg, match) => {
    const chatId = String(msg.chat.id);
    const userId = String(msg.from.id);
    const input = match[1] ? match[1].trim() : null;

    if (!input) {
      await bot.sendMessage(msg.chat.id,
        `🚨 *Incident Response*\n\nUsage: \`/incident <severity> <description>\`\n\n` +
        `Severities: ${SEVERITIES.map(s => `\`${s}\``).join(', ')}\n\n` +
        `Example:\n\`/incident high Unauthorized SSH login detected\``,
        { parse_mode: 'Markdown' }
      );
      return;
    }

    const parts = input.split(/\s+/);
    const rawSeverity = parts[0].toLowerCase();
    const description = parts.slice(1).join(' ').trim();

    if (!SEVERITIES.includes(rawSeverity)) {
      await bot.sendMessage(msg.chat.id,
        `❓ Unknown severity: \`${rawSeverity}\`\n\nValid: ${SEVERITIES.join(', ')}`,
        { parse_mode: 'Markdown' }
      );
      return;
    }

    if (!description) {
      await bot.sendMessage(msg.chat.id,
        `⚠️ Please add a description.\n\nExample: \`/incident high Unauthorized SSH login detected\``,
        { parse_mode: 'Markdown' }
      );
      return;
    }

    const severityEmoji = { low: '🟢', medium: '🟡', high: '🟠', critical: '🔴' }[rawSeverity] || '⚪';

    try {
      await confirmationGate({
        action: 'incident',
        args: { severity: rawSeverity, description },
        chatId,
        userId,
        sendMessage: (cid, text) => bot.sendMessage(cid, text, { parse_mode: 'Markdown' }),
        executor: async () => {
          if (logActivity) {
            try { logActivity('incident_logged', rawSeverity, description); } catch (_) {}
          }
          await bot.sendMessage(msg.chat.id,
            `${severityEmoji} *Incident logged:* \`${rawSeverity.toUpperCase()}\`\n📝 ${description}`,
            { parse_mode: 'Markdown' }
          );
        }
      });
    } catch (err) {
      await bot.sendMessage(msg.chat.id, `❌ Incident error: ${err.message}`);
    }
  });
}

module.exports = { registerIncident };