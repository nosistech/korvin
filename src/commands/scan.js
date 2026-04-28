// src/commands/scan.js
// /scan command — HIGH risk, requires confirmation

'use strict';

/**
 * registerScan(bot, { requestConfirmation, logActivity })
 *
 * Registers the /scan command on the bot instance.
 * Routes through confirmation gate before executing any scan.
 *
 * @param {TelegramBot} bot
 * @param {object} deps - { requestConfirmation, logActivity }
 */
function registerScan(bot, deps) {
  const { requestConfirmation, logActivity } = deps;

  bot.onText(/\/scan(?:\s+(.+))?/, async (msg, match) => {
    const chatId = String(msg.chat.id);
    const userId = String(msg.from.id);
    const target = match[1] ? match[1].trim() : 'full-system';

    // Route through confirmation gate — HIGH risk
    const pendingId = `scan_${Date.now()}`;
    const actionDescription = `Security scan: *${target}*`;

    const gateResult = requestConfirmation({
      pendingId,
      chatId,
      userId,
      risk: 'HIGH',
      action: 'scan',
      target,
      description: actionDescription
    });

    await bot.sendMessage(
      msg.chat.id,
      `🔴 *HIGH RISK — Scan Request*\n\n` +
      `Target: \`${target}\`\n` +
      `Action: Run security scan\n\n` +
      `To confirm: \`/confirm ${gateResult.pendingId}\`\n` +
      `To cancel: \`/cancel ${gateResult.pendingId}\`\n\n` +
      `⏱ Expires in 5 minutes.`,
      { parse_mode: 'Markdown' }
    );

    if (logActivity) {
      try { logActivity('scan_requested', target, `Pending ID: ${gateResult.pendingId}`); } catch (_) {}
    }
  });
}

module.exports = { registerScan };