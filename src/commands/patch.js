// src/commands/patch.js
// /patch command — HIGH risk, requires confirmation

'use strict';

/**
 * registerPatch(bot, { requestConfirmation, logActivity })
 *
 * Registers the /patch command on the bot instance.
 * Uses the confirmation gate before executing any patch action.
 *
 * @param {TelegramBot} bot
 * @param {object} deps - { requestConfirmation, logActivity }
 */
function registerPatch(bot, deps) {
  const { requestConfirmation, logActivity } = deps;

  bot.onText(/\/patch(?:\s+(.+))?/, async (msg, match) => {
    const chatId = String(msg.chat.id);
    const userId = String(msg.from.id);
    const target = match[1] ? match[1].trim() : null;

    if (!target) {
      await bot.sendMessage(
        msg.chat.id,
        '⚠️ *Usage:* `/patch <package-or-target>`\n\nExample: `/patch openssl`',
        { parse_mode: 'Markdown' }
      );
      return;
    }

    // Route through confirmation gate — HIGH risk
    const pendingId = `patch_${Date.now()}`;
    const actionDescription = `Apply security patch: *${target}*`;

    const gateResult = requestConfirmation({
      pendingId,
      chatId,
      userId,
      risk: 'HIGH',
      action: 'patch',
      target,
      description: actionDescription
    });

    await bot.sendMessage(
      msg.chat.id,
      `🔴 *HIGH RISK — Patch Request*\n\n` +
      `Target: \`${target}\`\n` +
      `Action: Apply system/package patch\n\n` +
      `To confirm: \`/confirm ${gateResult.pendingId}\`\n` +
      `To cancel: \`/cancel ${gateResult.pendingId}\`\n\n` +
      `⏱ Expires in 5 minutes.`,
      { parse_mode: 'Markdown' }
    );

    if (logActivity) {
      try { logActivity('patch_requested', target, `Pending ID: ${gateResult.pendingId}`); } catch (_) {}
    }
  });
}

module.exports = { registerPatch };