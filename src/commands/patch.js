// src/commands/patch.js
// /patch command — HIGH risk, uses confirmationGate

'use strict';

function registerPatch(bot, deps) {
  const { confirmationGate, logActivity } = deps;

  bot.onText(/\/patch(?:\s+(.+))?/, async (msg, match) => {
    const chatId = String(msg.chat.id);
    const userId = String(msg.from.id);
    const target = match[1] ? match[1].trim() : null;

    if (!target) {
      await bot.sendMessage(msg.chat.id,
        '⚠️ *Usage:* `/patch <package-or-target>`\n\nExample: `/patch openssl`',
        { parse_mode: 'Markdown' }
      );
      return;
    }

    try {
      await confirmationGate({
        action: 'patch',
        args: { target },
        chatId,
        userId,
        sendMessage: (cid, text) => bot.sendMessage(cid, text, { parse_mode: 'Markdown' }),
        executor: async () => {
          if (logActivity) {
            try { logActivity('patch_executed', target, 'Patch confirmed and executed.'); } catch (_) {}
          }
          await bot.sendMessage(msg.chat.id,
            `✅ *Patch executed:* \`${target}\`\n\n_Stub — wire real patch logic here._`,
            { parse_mode: 'Markdown' }
          );
        }
      });
    } catch (err) {
      await bot.sendMessage(msg.chat.id, `❌ Patch error: ${err.message}`);
    }
  });
}

module.exports = { registerPatch };