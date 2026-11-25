# Changelog

This file lists the changes in each version of Korvin.
The entries in `docs/DECISION_LOG.md` give the reasons and the numbers.

## 0.3.0: 2026-11-24

The final eval run and the release were on 2026-11-24.

### Changed

- Korvin sends a temperature of 0.6 and a presence penalty of 0 with each request (D-023).
  They replace the values stored in the model. In a control run, they raised the pass count from 923 to 962 of 1,080 trials.
- The line cap of the `korvin` package rose from 2,500 to 5,000 lines (D-026). The package has 2,496 lines.
- The evals stop the warm-up reply after 4,000 characters (D-033). This changed only the eval code.

### Tested and not kept

- Ten other experiments changed nothing in the released code (D-021, D-022, and D-024 to D-032).
  They tested a refused-read message, thinking off, a direct read, a clarifying sentence, and a coder chat format.
  They also tested a worked example, a finish check, a search tool, note keywords, and speed over several turns.

### Added

- The license: Apache 2.0, with a `NOTICE` file (D-035).
- New eval families: tool servers (18), finding facts in many files (19), and recall of notes by meaning (20).

### Measured

- The final full run passed 1,238 of 1,407 trials (88%), with Qwen 3.5 2B at a 64k context (D-034).
- The web search example reached Ollama's hosted service. The service answered with error 402: web search needs paid credits (D-036).
- A test against three other agent tools on the same model: Pi 100 of 110, Korvin 99, OpenCode 72, goose 51 (D-037).

## 0.2.0

### Added

- Korvin asks before it reads a file that you did not name, once a file or note entered the request (D-020).
- Korvin breaks chat-format markers in every tool result (D-020).
- Korvin reads the real token count, warns at 80% full, and stops before the 64k limit (D-020).
- Korvin keeps your standing rules and sends them with every request (D-020).
- Korvin marks model text that imitates its own action lines (D-020).
- Korvin tells you when it removes a failed turn (D-020).
- The sealed log and the `check` command.
- Local tool servers over MCP, with risk levels, tool approval, and fingerprints (D-010).
- The guided first-run setup.

The last three parts were built after the first baseline run.
An eval run of 0.2.0 used the tool servers. The records do not show the exact version of the other two.

### Measured

- Private files stolen by a hidden order fell from 11 of 50 to 0 of 50 (D-020).
- The full run of 0.2.0 passed 1,122 of 1,287 trials (87%) (D-034).

## 0.1.0

### Added

- Chat with one local model through Ollama, in a terminal.
- Four built-in tools: list a folder, read a file, save a note, and find a note.
- Permission questions. Enter alone always means "no" (D-009).
- The evals: tasks for the real model, graded by a program (D-008, D-018).

### Measured

- The first full baseline passed 957 of 1,257 trials (D-019).
  After three unfair checks were fixed, the same run counts 1,076 of 1,257 (86%) (D-020).
