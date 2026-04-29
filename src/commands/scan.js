// src/commands/scan.js
// /scan command — HIGH risk, uses confirmationGate

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
          if (logActivity) {
            try { logActivity('scan_executed', target, 'Scan confirmed and executed.'); } catch (_) {}
          }
          await bot.sendMessage(msg.chat.id,
            `✅ *Scan executed:* \`${target}\`\n\n_Stub — wire real scan logic here._`,
            { parse_mode: 'Markdown' }
          );
        }
      });
    } catch (err) {
      await bot.sendMessage(msg.chat.id, `❌ Scan error: ${err.message}`);
    }
  });
}

module.exports = { registerScan };