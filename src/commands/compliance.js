// src/commands/compliance.js
// /compliance command — MEDIUM risk, uses confirmationGate

'use strict';

const FRAMEWORKS = ['soc2', 'iso27001', 'nist', 'cis', 'gdpr', 'hipaa', 'pci'];

function registerCompliance(bot, deps) {
  const { confirmationGate, logActivity } = deps;

  bot.onText(/\/compliance(?:\s+(.+))?/, async (msg, match) => {
    const chatId = String(msg.chat.id);
    const userId = String(msg.from.id);
    const framework = match[1] ? match[1].trim().toLowerCase() : null;

    if (!framework) {
      await bot.sendMessage(msg.chat.id,
        `🔵 *Compliance Check*\n\nUsage: \`/compliance <framework>\`\n\nSupported:\n` +
        FRAMEWORKS.map(f => `• \`${f}\``).join('\n'),
        { parse_mode: 'Markdown' }
      );
      return;
    }

    if (!FRAMEWORKS.includes(framework)) {
      await bot.sendMessage(msg.chat.id,
        `❓ Unknown framework: \`${framework}\`\n\nSupported: ${FRAMEWORKS.join(', ')}`,
        { parse_mode: 'Markdown' }
      );
      return;
    }

    try {
      await confirmationGate({
        action: 'compliance',
        args: { framework },
        chatId,
        userId,
        sendMessage: (cid, text) => bot.sendMessage(cid, text, { parse_mode: 'Markdown' }),
        executor: async () => {
          if (logActivity) {
            try { logActivity('compliance_executed', framework, 'Compliance check run.'); } catch (_) {}
          }
          await bot.sendMessage(msg.chat.id,
            `✅ *Compliance check:* \`${framework.toUpperCase()}\`\n\n_Stub — wire real compliance logic here._`,
            { parse_mode: 'Markdown' }
          );
        }
      });
    } catch (err) {
      await bot.sendMessage(msg.chat.id, `❌ Compliance error: ${err.message}`);
    }
  });
}

module.exports = { registerCompliance };