// src/commands/incident.js
// /incident command — MEDIUM risk, requires confirmation

'use strict';

const SEVERITIES = ['low', 'medium', 'high', 'critical'];

/**
 * registerIncident(bot, { requestConfirmation, logActivity })
 *
 * @param {TelegramBot} bot
 * @param {object} deps - { requestConfirmation, logActivity }
 */
function registerIncident(bot, deps) {
  const { requestConfirmation, logActivity } = deps;

  bot.onText(/\/incident(?:\s+(.+))?/, async (msg, match) => {
    const chatId = String(msg.chat.id);
    const userId = String(msg.from.id);
    const input = match[1] ? match[1].trim() : null;

    if (!input) {
      await bot.sendMessage(
        msg.chat.id,
        `🚨 *Incident Response*\n\n` +
        `Usage: \`/incident <severity> <description>\`\n\n` +
        `Severities: ${SEVERITIES.map(s => `\`${s}\``).join(', ')}\n\n` +
        `Example:\n\`/incident high Unauthorized SSH login detected\``,
        { parse_mode: 'Markdown' }
      );
      return;
    }

    // Parse severity + description
    const parts = input.split(/\s+/);
    const rawSeverity = parts[0].toLowerCase();
    const description = parts.slice(1).join(' ').trim();

    if (!SEVERITIES.includes(rawSeverity)) {
      await bot.sendMessage(
        msg.chat.id,
        `❓ Unknown severity: \`${rawSeverity}\`\n\nValid: ${SEVERITIES.join(', ')}`,
        { parse_mode: 'Markdown' }
      );
      return;
    }

    if (!description) {
      await bot.sendMessage(
        msg.chat.id,
        `⚠️ Please provide a description after the severity.\n\nExample: \`/incident high Unauthorized SSH login detected\``,
        { parse_mode: 'Markdown' }
      );
      return;
    }

    // Route through confirmation gate — MEDIUM risk
    const pendingId = `incident_${Date.now()}`;
    const severityEmoji = { low: '🟢', medium: '🟡', high: '🟠', critical: '🔴' }[rawSeverity] || '⚪';

    const gateResult = requestConfirmation({
      pendingId,
      chatId,
      userId,
      risk: 'MEDIUM',
      action: 'incident',
      target: rawSeverity,
      description: `[${rawSeverity.toUpperCase()}] ${description}`
    });

    await bot.sendMessage(
      msg.chat.id,
      `🟡 *MEDIUM RISK — Incident Report*\n\n` +
      `${severityEmoji} Severity: \`${rawSeverity.toUpperCase()}\`\n` +
      `📝 Description: ${description}\n\n` +
      `To confirm: \`/confirm ${gateResult.pendingId}\`\n` +
      `To cancel: \`/cancel ${gateResult.pendingId}\`\n\n` +
      `⏱ Expires in 5 minutes.`,
      { parse_mode: 'Markdown' }
    );

    if (logActivity) {
      try {
        logActivity('incident_reported', rawSeverity, description);
      } catch (_) {}
    }
  });
}

module.exports = { registerIncident };