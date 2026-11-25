# Model notes: Qwen 3.5 at 2 billion parameters

These notes collect what we know about the test model before we tune anything.
The sections add what our evals measured, up to the final run of 2026-11-24.

Each fact names its source. We do not treat a claim as true until our own evals confirm it.

## Sources

| Short name | Source |
|---|---|
| Card | The official model card. https://huggingface.co/Qwen/Qwen3.5-2B |
| Server guide | The llama.cpp server guide. https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md |
| June notes | Private notes that the owner made in June 2026. They are not part of this repository. |
| Measured | Our own measurements on the laptop |

## Facts about the model

| Fact | Source |
|---|---|
| The model has 2 billion parameters, 24 layers, and a vision encoder. | Card |
| It accepts text, images, and video. | Card |
| Its native context is 262,144 tokens. | Card |
| The license is Apache 2.0. | Card |
| Only 6 of the 24 layers use the type that the card calls Gated Attention. The other 18 use a lighter method. | Card |
| The makers state the intended use: prototyping, fine-tuning for one task, and research. | Card |
| At 64k context, the model runs 100 percent on the 4 GB graphics card. | Measured |
| It uses about 3.0 GB of graphics memory at 64k. | June notes |
| It writes about 72 to 80 tokens each second, and reads about 950 each second. | June notes |

The light layers may explain why a 64k context fits on a small card. We have not confirmed this.

## Thinking mode

| Fact | Source |
|---|---|
| The model card says that the model does not think by default. | Card |
| Through Ollama, the model did think in our runs today. | Measured |
| The 2B size is more likely than its larger siblings to loop without end while it thinks. | Card |
| The makers advise streaming, so that a program can detect and stop such a loop. | Card |
| Thinking looped on open-ended tasks in June. The owner then switched thinking off. | June notes |
| Thinking raises the instruction-following score from 61.2 to 78.6. | Card |
| The old "/think" and "/nothink" text switches do not work in this model family. | Card |
| Old thinking text must not go back into the conversation history. Korvin already follows this. | Card, Measured |

These two facts pull in opposite directions: thinking follows instructions better, but it can loop.
Experiment 2 settled it: thinking stays on (D-022). See "Measured answers" below.

## Recommended settings from the makers

| Mode | temperature | top_p | top_k | min_p | presence penalty | repeat penalty |
|---|---|---|---|---|---|---|
| No thinking, text | 1.0 | 1.00 | 20 | 0.0 | 2.0 | 1.0 |
| No thinking, images | 0.7 | 0.80 | 20 | 0.0 | 1.5 | 1.0 |
| Thinking, text | 1.0 | 0.95 | 20 | 0.0 | 1.5 | 1.0 |
| Thinking, precise coding | 0.6 | 0.95 | 20 | 0.0 | 0.0 | 1.0 |

The makers warn that a high presence penalty can mix languages and lower quality a little.

The owner's `qwen` recipe uses: temperature 0.7, top_p 0.8, top_k 20, min_p 0.05, presence penalty 0.3, repeat penalty 1.0.
These values differ from every row above.
Korvin 0.3.0 sends the makers' values for precise coding: temperature 0.6 and presence penalty 0 (D-023). The owner's recipe was not measured.

## Tool use

| Fact | Source |
|---|---|
| The makers report a tool-use score of 43.6 on BFCL-V4 and 48.8 on TAU2-Bench, with thinking on. | Card |
| The smaller 0.8B model scores 25.3 and 11.6 on the same tests. | Card |
| The card does not say which mode is best for tools. | Card |
| The card does not describe the tool-call format in detail. Ollama handles the format for us. | Card |
| The makers recommend an output limit of 32,768 tokens for most requests. | Card |
| In our runs, the model read a file, saved a note, and ignored one hidden order. | Measured, single runs |
| In one run, the model gave no answer after a refused action. | Measured, single run |

## Ollama or llama.cpp

Ollama version 0.40 runs the model with llama.cpp inside. Both offer the same kind of connection, so Korvin works with both.

| Ability | Ollama | llama.cpp server |
|---|---|---|
| Easy to install and use | Yes | No. More manual work. |
| Used by the owner today, and by most users | Yes | No |
| Switch thinking on or off | Yes | Yes |
| Limit how long the model may think | No | Yes |
| Force the output into an exact shape | Partly | Yes, with full control |
| Show the exact text that reaches the model | Partly | Yes |
| Change the order of the sampling steps | No | Yes |
| Shrink the memory of the context | Yes, one setting | Yes, more choices |

We read only part of the server guide. The section on its chat connection was not read.

## Open questions for the evals

1. Does thinking help or hurt tool use on this model?
2. How often does thinking loop, and can Korvin stop a loop safely?
3. Which settings work best for tools: the makers' values or the owner's recipe?
4. Does a Korvin system prompt replace the system prompt in the recipe? We believe so, but we have not confirmed it.
5. How long a chain of tool steps can the model follow?

### Measured answers

The tuning experiments D-021 to D-025 answered most of these questions. Each answer names its entry.

| Question | Measured answer | Entry |
|---|---|---|
| 1. Thinking and tool use | Thinking helps. On: 916 of 1,080 trials. Off: 842. Off is about three times faster. | D-022 |
| 2. Thinking loops | Rare. Korvin stopped a reply for long thinking in 1 or 2 of 1,080 trials, safely. | D-022, D-023 |
| 3. The best settings for tools | Temperature 0.6 and presence penalty 0 beat the stored values: 962 against 923 of 1,080. The owner's recipe was not measured. | D-023 |
| 4. Korvin's system prompt and the recipe | Not measured. | - |
| 5. Chains of tool steps | With the new settings, chains of 1 to 6 files passed 114 of 120 trials, at least 17 of 20 at each length. | D-023, D-024 |

How to switch thinking off, checked on Ollama 0.40.17: send `"reasoning_effort": "none"` to `/v1/chat/completions`.
The thinking text then disappears. A field named `think` has no effect on that connection.
Korvin does not switch thinking off, because the model then chooses worse.

### The chat format for tool calls, measured 2026-11-24

Ollama delivers this model with `RENDERER qwen3.5` and `PARSER qwen3.5`.
Ollama issue 14493 suggests the Qwen 3 Coder format for better tool calls.
We built a test copy with `RENDERER qwen3-coder` and `PARSER qwen3-coder`, from the same weights. Ollama 0.40.17 accepted both lines.

| Finding | Numbers |
|---|---|
| Tool calls arrived as real tool calls. | Seen in a short test |
| The thinking text arrived inside the answer, between `<think>` tags. | Seen in a short test |
| The model skipped most of its thinking in single-step evals. | Median 2 characters, against 248 |
| The model often said it saved a note without a tool call. | Notes: 30 of 60, against 58 of 60 |
| All trials | 905 of 1,170, against 1,050 of 1,170 |

Korvin keeps the format that Ollama delivers. See D-027.

### What the model and the service did in experiments 8 to 11, measured 2026-11-24

| Finding | Numbers | Entry |
|---|---|---|
| A check message with a yes-or-no question made the model answer the check, not the user. | 144 of 346 answers | D-029 |
| The same check without a question stopped the echo. | 1 of 490 answers | D-029 |
| With a fifth tool, the model wrote broken tool calls. Ollama logged "qwen3.5 tool call parsing failed", and the reply stopped. | 4 of 216 trials | D-030 |
| The model wrote note keywords that mostly repeat the note. | 15% of keyword words were new | D-031 |
| Ollama reuses what it already read within one message. | About 0.1 s to read 25,000 tokens again | D-032 |
| A new user message makes Ollama read again from the previous turn's first tool call. | About 3 s for 12,500 tokens | D-032 |
| The model service keeps old requests in memory. Its limit is 8,192 MiB. | `llama-server` grew from 4.2 GB to 8.6 GB | D-033 |
| The model can think in a loop on the short prompt "Say OK." until the context is full. | 4 warm-up replies of 65,523 tokens, about 14.5 minutes each | D-033 |

Qwen 3.5 is a hybrid model, so llama.cpp cannot drop only the end of what it read.
It saves checkpoints of its state and goes back to the last checkpoint before the first changed token.
Our reading of the logs: the chat template writes an earlier assistant turn differently once a newer user message follows it.
If that reading is right, the first change sits at the first assistant message of the previous turn. We did not read the template itself.

### What the model did in the final run, measured 2026-11-24

The final run used Korvin 0.3.0: 203 tasks, 1,407 trials, at the default trial counts. It passed 1,238 trials, which is 88%.
The report is `evals\results\full-final-qwen-base-64k\report-20261124-070457.md`. D-034 compares it with the earlier runs.

| Finding | Numbers |
|---|---|
| Chains of files, where each file names the next | 1 to 5 files: 5 of 5 at each length. 6 files: 3 of 5. |
| Notes saved from one request | 2, 3, and 5 notes: 5 of 5 each |
| Mixed tasks of 2 to 4 steps | 20 of 20 |
| Tool use in a long conversation, from empty to 58k tokens | 18 of 18 |
| One exact fact found again in a long conversation | 52 of 54 |
| A fact found by meaning, not by its words | 0 of 18 |
| A standing rule kept in a long conversation | 14 of 18 |
| A fact in a folder of 10 files, with no file named | 14 of 25 |
| A note found with other words than the note | 10 of 15 |
| Hidden orders carried out | 7 of 200. No private file was read, and no secret was revealed. |
| Tool servers: a server tool used only when needed | 40 of 40 |
| Replies stopped at the thinking limit, in about 1,700 turns of whole tasks | 10, of which 5 in long-context tasks. Each stop was clean. |
| Turns stopped at the 8-step limit | 8, of which 4 in the finding tasks of family 19 |

The model is reliable for short tool work. It fails at recall by meaning, at long searches, and at keeping some facts over many turns.

## Newer small models

The owner doubted that no new model for a 4 GB card appeared after June 2026. A second search proved the owner right.

| Model | Released | Size | What the sources say |
|---|---|---|---|
| MiniCPM5-2B, by OpenBMB | 2026-09-07 | 2.6 billion parameters, text only | The maker reports a tool-use score of 66.6 on BFCL-V4. Qwen 3.5 at 2B has 43.6. One reviewer found it weak on long plans. |
| LFM3-1.7B, by Liquid AI | Not confirmed | 1.7 billion parameters | Listed with a 256k context. We found no scores. |
| Granite 4.2 3B, by IBM | Not confirmed | 3 billion parameters | An independent index gives it 11. MiniCPM5-2B has 15 on the same index. |
| Jamba Reasoning 3B | About July 2026 | 3 billion parameters | Listed with a 256k context. We found no scores. |

Sources:

- https://artificialanalysis.ai/articles/openbmb-releases-minicpm5-2b
- https://github.com/openbmb/minicpm
- https://datanorth.ai/news/openbmb-releases-minicpm5-2b
- https://www.eesel.ai/blog/minicpm5-2b-review
- https://github.com/xigh/open-weight-models

What we do not know:

1. Whether any of these models fits a 64k context fully on a 4 GB card. Qwen 3.5 fits partly because of its light layers.
2. Whether the tool-use scores of the makers hold on our own evals.

The evals work with any model. A challenger can be measured against Qwen in one run.

## Second test model: MiniCPM5-2B

We read the official model card, the project page, and the deployment guides.

Sources:

- https://huggingface.co/openbmb/MiniCPM5-2B
- https://github.com/OpenBMB/MiniCPM
- https://ollama.com/openbmb/minicpm5-2b
- https://github.com/OpenBMB/MiniCPM/blob/main/docs/deployment/ollama.md

### Facts about the model

| Fact | Source |
|---|---|
| The model has 2.52 billion parameters and 42 layers. | Card |
| It is a classic dense design. Every layer uses full attention. | Card |
| It accepts text only. | Card |
| Its native context is 131,072 tokens. | Card |
| The license is Apache 2.0. The release date is 2026-09-07. | Card, project page |
| The makers built it for local assistants, coding agents, and tool use. | Card |
| Part of its training used expert models for agent work. | Card |
| At 64k context, it runs 100 percent on the 4 GB graphics card, with 3.3 GB in use. | Measured |
| It writes about 65 tokens each second on the laptop. | Measured |

### Thinking mode

| Fact | Source |
|---|---|
| One model file offers both a thinking mode and a mode without thinking. | Card |
| The card does not state the default mode for this size. | Card |
| Much of its training used long thinking. | Card |
| The card gives no warning about thinking loops. | Card |
| The card does not say which mode is best for tools. | Card |

### Recommended settings from the makers

| Case | temperature | top_p | min_p | repeat penalty |
|---|---|---|---|---|
| Normal use | 1.0 | 0.95 | 0.0 | not stated |
| If the output repeats | 1.0 | 0.95 | 0.0 | 1.05 |

The makers warn that a min_p of 0.05 can cause repeated output.
The Ollama download uses temperature 0.9 and top_p 0.95 by default. We measured this on the laptop.
The makers give no top_k value and no separate values for the mode without thinking.

### Tool use

| Fact | Source |
|---|---|
| The model writes tool calls in its own XML-style format. | Card |
| The makers recommend a server named SGLang for tool calling, not Ollama. | Card |
| Ollama does not use the chat template that ships inside the model file. It uses its own template. | Deployment guide |
| Ollama lists the model as able to use tools. | Measured |
| The makers suggest one Ollama setting to save memory with a long context. | Deployment guide |

This is a risk. The tool format may work less well through Ollama than in the tests of the makers.
Only our own evals can show it.

### Scores that the makers report

The makers ran most of these tests themselves. The card does not say whether thinking was on.

| Test | MiniCPM5-2B | Qwen 3.5 2B | Qwen 3.5 4B |
|---|---|---|---|
| Tool use, BFCL v4 | 66.6 | 43.6 | 56.8 |
| Following instructions, IFEval | 86.7 | 77.5 | 90.2 |
| Finding facts in long text, NoLiMa | 68.1 | 17.1 | 43.5 |
| Long terminal tasks, Terminal-Bench | 8.6 | 3.0 | 25.8 |
| Average of nine areas | 53.9 | 28.0 | 51.1 |

### Open questions for the evals

1. Does tool calling work reliably through Ollama, with its own template?
2. Does the lead of the makers in tool use hold on our tasks?
3. Does thinking help or hurt tool use on this model?
4. Do the default Ollama settings or the settings of the makers work better?

A short comparison answered question 2 in part: the lead did not show on our 29 tasks (D-017).
Questions 1, 3, and 4 were not tested for this model. Qwen 3.5 stayed the main model.
