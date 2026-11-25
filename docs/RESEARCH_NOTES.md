# Research notes

The first sections of these notes list the sources behind entry D-009 of the decision log.
(Correction: an earlier version of this line named D-014 by mistake.)

Some sources are company blogs or second-hand reports. We mark those as weaker evidence.

## People approve permission questions without reading

- Paper: "How Agents Ask for Permission". https://arxiv.org/pdf/2607.13718
- Paper: "Don't Let AI Agents YOLO Your Files". https://arxiv.org/pdf/2604.13536
- Paper: the 2026 Singapore Consensus on AI safety research. https://arxiv.org/pdf/2608.14611
- Article on permission fatigue. https://scalex.dev/blog/ai-agent-permissions/
- Article on approval patterns. https://dev.to/kunal_d6a8fea2309e1571ee7/10-hitl-tool-approval-patterns-for-ai-agents-2026-17ba
- Weaker evidence: the 93 percent figure reaches us through second-hand reports.

## Open ports and harmful skills in a popular open assistant

- The Register, January 2026. https://www.theregister.com/2026/01/27/clawdbot_moltbot_security_concerns
- VentureBeat. https://venturebeat.com/security/clawdbot-exploits-48-hours-what-broke
- eSecurity Planet. https://www.esecurityplanet.com/threats/openclaws-rapid-rise-exposes-thousands-of-ai-agents-to-the-public-internet/
- Snyk study of harmful skills. https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/
- The counts differ between companies, because they measured on different dates.

## Tool servers can hide orders or change after approval

- Paper on security problems in the MCP ecosystem. https://arxiv.org/html/2510.16558v1
- Paper on MCP client security. https://arxiv.org/html/2603.22489v1
- Cloud Security Alliance paper, May 2026. https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/05/CSA_whitepaper_mcp_security_tool_poisoning_20260506-csa-styled.pdf
- Snyk guide on detecting poisoned tools. https://labs.snyk.io/resources/detect-tool-poisoning-mcp-server-security/

## First-run problems in other assistants

- Review of nine assistants, August 2026. https://www.digitalapplied.com/blog/ai-cli-first-run-traps-census
- GitLab design note for a first-run welcome. https://gitlab.com/groups/gitlab-org/-/work_items/22187

## Small local models and tools

- Docker test of local models for tool use. https://www.docker.com/blog/local-llm-tool-calling-a-practical-evaluation/
- Test of seven models with a coding agent. https://dev.to/kuroko1t/what-happens-when-local-llms-fail-at-tool-calling-testing-7-models-with-a-rust-coding-agent-cep
- Four failure types in multi-step work. https://dev.to/thlandgraf/four-failure-modes-youll-hit-running-a-local-llm-in-a-multi-step-agentic-loop-3kd9
- Gap: we found no test on a 4 GB graphics card. Our own evals will fill this gap.
- Update, 2026-11-24: our evals now cover one 4 GB card, the RTX 3050 Ti laptop card. See D-034 in the decision log.

## General complaints about assistants

- Developer discussion on GitHub. https://github.com/orgs/community/discussions/210331
- One year of coding assistant complaints. https://openchamber.dev/blog/ai-coding-complaints/
- Study of 3,222 enterprise reviews. https://learn.g2.com/ai-agent-adoption-trends-enterprises-2026

## Installing Python programs for non-developers

- Guide on shipping a Python program to end users. https://pydevtools.com/handbook/explanation/how-do-i-ship-a-python-application-to-end-users/

## Gaps

- The search found few direct Reddit or forum threads. A second research round should target them.
- We did not test any competing assistant by hand.

## Second round: which models can use tools, and which can be tricked

These sources are behind entry D-017 of the decision log.

- Open benchmark of 21 local models on tool use. https://github.com/MikeVeerman/tool-calling-benchmark
- Guide that puts the practical floor near 4 billion parameters. https://d-central.tech/local-llm-agent-capability/
- Comparison of three small models on tool use. https://www.ertas.ai/blog/on-device-tool-calling-2026-qwen3-gemma4-phi4
- Paper on tool use in models under 2 billion parameters. https://arxiv.org/pdf/2609.07370
- Independent analysis of the Qwen 3.5 small models. https://artificialanalysis.ai/articles/qwen3-5-small-models
- Study of hidden instructions in small models. https://huecodes.github.io/research/prompt-injection
- Test of 42 models against hidden instructions. https://www.lesswrong.com/posts/jrfEYXFyqkuWLfGCa/role-boundary-plasticity-prompt-injection-gauntlet-reveals-1
- Report on a hosted browser agent and its safeguards. https://venturebeat.com/security/anthropic-browser-agent-hijacked-31-percent-before-safeguards-engaged
- Weaker evidence: most of these are blog tests or papers without peer review.
- Gap: we found no official tool-use ranking that includes Qwen 3.5 at 2 billion parameters.


---

## Later research: tool servers, web search, framework names, hidden orders

A research helper collected these facts from the web. We have not tested them ourselves.
"Not confirmed" means that the helper found no reliable source.

### The tool-server protocol (MCP)

| Fact | Source |
|---|---|
| The newest version is `2026-07-28`. It has no start handshake. Each request carries the version. | https://modelcontextprotocol.io/specification/2026-07-28/basic/index.md |
| Older servers use version `2025-11-25` or earlier, with an `initialize` handshake. | https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle |
| A client must support both kinds. It tries the new kind first, then the old kind. | https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning.md |
| A local server talks through its standard input and output, with one JSON message on each line. | https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio.md |
| To stop a server, the client closes its input, waits, and then ends the process. | Same page |
| The client must show tool inputs, ask before sensitive calls, and use time limits. | https://modelcontextprotocol.io/specification/2026-07-28/server/tools.md |
| A server can hide orders in a tool description, or change a description after approval. | https://owasp.org/www-project-mcp-top-10/ |
| The usual defence is to store a fingerprint of each tool at approval, and to ask again after a change. | Several write-ups |
| No study measures how many tools a model of 1 to 4 billion parameters can handle. | Not confirmed |

### Web search options

| Option | Key needed | Main risk |
|---|---|---|
| Ollama web search | Free Ollama account and key | The free limits are not published. Queries leave the computer. |
| Tavily | Free key, 1,000 searches each month | A second company. |
| Brave Search | Key, and probably a payment card | The free tier ended for new users. |
| DuckDuckGo page | None | Blocking, and unclear terms for automated use. |
| Local SearXNG | None | The setup is too hard for most users. |

No search server exists as one plain Python file with no packages. The common ones need Node or `uv`.

### Framework names to verify

| Framework | Facts |
|---|---|
| OWASP Top 10 for LLM Applications 2025 | LLM01 Prompt Injection to LLM10 Unbounded Consumption. Source: https://genai.owasp.org/llm-top-10/ |
| OWASP Top 10 for Agentic Applications 2026 | Published 2025-12-09. ASI01 Agent Goal Hijack to ASI10 Rogue Agents. The titles came from a vendor page. Check the official file. |
| OWASP MCP Top 10 | Still a beta. MCP01 to MCP10. |
| MITRE ATLAS | Release v2026.10 of 2026-10-28. AML.T0051 LLM Prompt Injection, AML.T0053 AI Agent Tool Invocation, AML.T0010 Supply Chain Compromise. |

Correction: the check for the security map corrected these ATLAS facts.

- AML.T0057 LLM Data Leakage no longer exists in release v2026.10. Its content moved to AML.T0085.002.
- AML.T0010 is named "Supply Chain Compromise" in v2026.10. Earlier releases called it "AI Supply Chain Compromise".
| NIST AI RMF | Govern, Map, Measure, Manage. The Generative AI Profile is NIST AI 600-1. |

### Defences against hidden orders

| Defence | Evidence |
|---|---|
| Mark outside text so that the model can tell it apart | Strong on large models. On an 8B model, 15 to 23% of attacks still succeeded. https://arxiv.org/html/2606.18530 |
| Repeat the user request after a tool result | A small gain. A clever attacker defeats it. |
| Make chat-format markers harmless | Logical for Qwen. No published number. |
| Ask the user before a sensitive action, once outside text entered the turn | Does not depend on the skill of the model. https://ai.meta.com/blog/practical-ai-agent-security/ |
| A second model that plans without seeing outside text | Too heavy for a 2B model on a 4 GB card. |

No source tested these defences on a model of 1 to 4 billion parameters. Our own evals must do it.
