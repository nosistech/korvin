// src/commands/compliance.js
// /compliance command — MEDIUM risk, requires confirmation

'use strict';

const FRAMEWORKS = ['soc2', 'iso27001', 'nist', 'cis', 'gdpr', 'hipaa', 'pci'];

/**
 * registerCompliance(bot, { requestConfirmation, logActivity })
 *
 * @param {TelegramBot} bot
 * @param {object} deps - { requestConfirmation, logActivity }
 */
function registerCompliance(bot, deps) {
  const { requestConfirmation, logActivity } = deps;

  bot.onText(/\/compliance(?:\s+(.+))?/, async (msg, match) => {
    const chatId = String(msg.chat.id);
    const userId = String(msg.from.id);
    const framework = match[1] ? match[1].trim().toLowerCase() : null;

    if (!framework) {
      await bot.sendMessage(
        msg.chat.id,
        `🔵 *Compliance Check*\n\n` +
        `Usage: \`/compliance <framework>\`\n\n` +
        `Supported frameworks:\n` +
        FRAMEWORKS.map(f => `• \`${f}\``).join('\n'),
        { parse_mode: 'Markdown' }
      );
      return;
    }

    if (!FRAMEWORKS.includes(framework)) {
      await bot.sendMessage(
        msg.chat.id,
        `❓ Unknown framework: \`${framework}\`\n\nSupported: ${FRAMEWORKS.join(', ')}`,
        { parse_mode: 'Markdown' }
      );
      return;
    }

    // Route through confirmation gate — MEDIUM risk
    const pendingId = `compliance_${Date.now()}`;
    const actionDescription = `Run ${framework.toUpperCase()} compliance check`;

    const gateResult = requestConfirmation({
      pendingId,
      chatId,
      userId,
      risk: 'MEDIUM',
      action: 'compliance',
      target: framework,
      description: actionDescription
    });

    await bot.sendMessage(
      msg.chat.id,
      `🟡 *MEDIUM RISK — Compliance Check*\n\n` +
      `Framework: \`${framework.toUpperCase()}\`\n` +
      `Action: Run compliance audit\n\n` +
      `To confirm: \`/confirm ${gateResult.pendingId}\`\n` +
      `To cancel: \`/cancel ${gateResult.pendingId}\`\n\n` +
      `⏱ Expires in 5 minutes.`,
      { parse_mode: 'Markdown' }
    );

    if (logActivity) {
      try { logActivity('compliance_requested', framework, `Pending ID: ${gateResult.pendingId}`); } catch (_) {}
    }
  });
}

module.exports = { registerCompliance };