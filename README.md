# Korvin

Korvin is a small, private AI assistant for the terminal, and it runs fully on your own computer.
We built and measured it for one small local model: Qwen 3.5 at 2 billion parameters, with a 64k context.

## Who Korvin is for

Korvin is for people with a graphics card of 4 GB or less who want a private assistant.
It is also for people who want to read and check every line of their assistant.

- Korvin talks only to a model on your own computer. Its own code never connects to the internet.
- It reads text files in one folder that you choose, and it saves and finds notes.
- It asks before every note, every tool server call, and every unexpected read.
- It keeps a sealed log of every action.
- It uses only the Python standard library. The package has under 2,500 lines.

We measured Korvin on one laptop with a 4 GB card. Smaller cards are not tested yet.

The current version is 0.3.0.

| Document | Content |
|---|---|
| [User guide](docs/USER_GUIDE.md) | How to install, use, and remove Korvin, with every measured number. |
| [Security map](docs/SECURITY_MAP.md) | Each safety control, linked to public security frameworks, and the risks that remain. |
| [Decision log](docs/DECISION_LOG.md) | Every important choice and its reasons, for readers who do not write code. |
| [Eval plan](docs/EVAL_PLAN.md) | Every kind of eval, and the research behind it. |
| [Changelog](CHANGELOG.md) | The changes in each version. |
| [Security policy](SECURITY.md) | How to report a security problem privately. |
| [Contributing](CONTRIBUTING.md) | How to run the tests, and the rules for a change. |

## Status

| Step | Content | State |
|---|---|---|
| 1 | Chat with the local model | Done. |
| 2 | Four built-in tools and permission questions | Done. |
| 3 | Evals and the baseline score | Done on 2026-11-24. The final full run passed 1,238 of 1,407 trials. See "Measured results" below. |
| 4 | Up to five tuning experiments | Done. One of five changes was kept: a lower temperature. See D-021 to D-025. |
| 4b | Six more experiments | Done on 2026-11-24. No change was kept: tool-call format, worked example, finish check, search tool, note keywords. A speed test found no fix to make. See D-027 to D-032. |
| 5 | The sealed log and the check command | Built. Tried with the real model. |
| 6 | Local tool servers, with web search | Built. Tried with the real model and the clock server. The web search example reached Ollama's service on 2026-11-24. The service refused it with error 402, because web search needs paid credits. Search results are tested only against a fake of the service. |
| 7 | Guided setup, user guide, security map check | Done. The setup was tried with the real model. The user guide and the security map match the final run of 2026-11-24. |
| 8 | First public release | In progress on 2026-11-24. The license is Apache 2.0 (D-035). Version 1.0 and the website update come later. |

The package `korvin\` has 2,496 lines. The cap is 5,000 lines (D-026).
Read [the decision log](docs/DECISION_LOG.md) for every choice and the reasons behind it.

## Measured results

The final eval run tested Korvin 0.3.0 on 2026-11-24, with Qwen 3.5 2B at a 64k context, fully on a 4 GB graphics card.
It ran 203 tasks in 1,407 trials and passed 1,238 of them, which is 88%. The run took 2 hours 22 minutes.
A program graded every trial. The full report is `evals\results\full-final-qwen-base-64k\report-20261124-070457.md`.

| What we measured | Result |
|---|---|
| Chains of files, where each file names the next | 1 to 5 files: 5 of 5 at each length. 6 files: 3 of 5. |
| Saving several notes from one request | 2, 3, and 5 notes: 5 of 5 each |
| Mixed tasks of 2 to 4 steps | 20 of 20 |
| Tool use in a long conversation, up to 58k tokens | 18 of 18 |
| Hidden orders in files and notes | 7 of 200 attacks worked. No private file was read, and no secret was revealed. |
| Tool servers: a server tool used only when needed | 40 of 40 |
| Finding a fact in a folder of 10 files, with no file named | 14 of 25 |
| Finding a fact by meaning, not by its words | 0 of 18 |

**Known limits.**

- The model is small. It fails at recall by meaning, at long searches, and at some facts over many turns.
- Most tasks ran only 5 times, so a task with "5 of 5" can still fail on the next run.
- A hidden order can still change what the model says, or make it refuse your task. The permission questions stop reads and saves, but they cannot stop what the model writes.
- We measured only one model on one computer. Cards below 4 GB, Mac, Linux, and pipx are not tested.
- The web search example has returned no search results yet, because Ollama's service asks for paid credits (D-036).
- An AI model, not a person, checked 40 trials by hand and agreed with the program on 38. No person has checked the checks yet.

Section 8 of `docs\USER_GUIDE.md` gives every number, and what to do about each weakness.

### Korvin and three other tools

On 2026-11-24, a test ran four terminal agent tools against the same model on the same computer.
It had 22 tasks, and each tool ran 110 trials. A program graded every trial.

| Tool | Passed | Median seconds | Timeouts | Trials with a broken tool call | Fixed prompt size (tokens) |
|---|---|---|---|---|---|
| Pi 1.5.2 | 100 of 110 (91%) | 4.1 | 5 | 0 | 1,515 |
| Korvin 0.3.0 | 99 of 110 (90%) | 2.8 | 0 | 0 | 744 |
| OpenCode 1.19.6 | 72 of 110 (65%) | 8.8 | 3 | 29 | 7,621 |
| goose 1.59.2 | 51 of 110 (46%) | 9.3 | 2 | 9 | 6,626 |

- Korvin and Pi are level. Korvin passed more trials than OpenCode and goose, and each of those p-values is below 0.001.
- With Korvin's sampling settings, Pi passed 105 of 110. That gap to Korvin is not statistically clear.
- Korvin was the fastest tool, and it never reached the time limit.
- In 9 of 10 trials, Korvin told the user what it cannot do. Pi did so in 3 of 10.
- Pi can create files, and Korvin cannot. Pi was also a little better at finding a file.
- A hidden order asked for a private file in the folder. Korvin's question stopped the read in 5 of 5 trials.
- In the other tools, the model read that file in 9 of 15 trials. With goose, it revealed the secret once.

We wrote the tasks ourselves. The other three tools are coding agents, and their makers did not design them for a model of this size.
Decision D-037 in the decision log gives both parts of the test and every limit. It also explains why the p-values are too optimistic.

Korvin 0.3.0 sends a temperature of 0.6 and a presence penalty of 0 with each request. They replace the values stored in the model.
They made tool work more reliable in our evals. Section 4.6 of `docs\USER_GUIDE.md` explains why, and how to change them.

## Install and first run

Korvin needs Python 3.11 or later, and Ollama with one model.
Korvin needs no other package when it runs.

1. Install Python 3.11 or later from https://www.python.org/downloads/.
2. Install Ollama from https://ollama.com/download, and start it.
3. Download the model that Korvin is built for: `ollama pull qwen3.5:2b-q4_K_M`
4. Download or clone this repository.
5. Start Korvin in one of the two ways below. The first time, a short guided setup starts.

**Way 1: start from this folder, with no install.**

1. Open a terminal in this folder.
2. Type `python -m korvin`.

**Way 2: install the `korvin` command once.**

1. Open a terminal in this folder.
2. Type `pip install .` with the dot at the end. If you use pipx, type `pipx install .` instead. The pipx install is not tested.
3. Type `korvin` to start Korvin, from any folder. `python -m korvin` also works.

The install needs the internet once. Pip downloads a small build tool, `flit_core`, to build Korvin.
Korvin itself has no dependencies. To remove the command, type `pip uninstall korvin`.
With the install, you can type `korvin` in place of `python -m korvin` in every command below.

The setup has five steps, and you edit no file:

1. Korvin checks that Ollama answers on this computer.
2. You choose one of your installed models by its number.
3. Korvin is built for a context of 65,536 tokens. If the model uses less, Korvin offers a 64k copy. You answer yes or no.
4. You choose the folder that Korvin may read, or no folder. Korvin refuses a whole drive, your home folder, and system folders.
5. Korvin shows a summary, with the copy if you asked for one. Nothing happens before your "yes".

After your "yes", Ollama makes the copy, and Korvin writes the settings file.
If Ollama cannot make the copy, Korvin tells you and keeps the base model in the settings.
Korvin writes no file, and Ollama makes no copy, before the setup is finished.
The settings, the notes, and the sealed log live in Korvin's own data folder.
On Windows, that is `%APPDATA%\Korvin`. Korvin never writes in the folder that you chose.

### Commands in the terminal

| Command | What it does |
|---|---|
| `python -m korvin` | Starts the chat. Without settings, it starts the guided setup first. |
| `python -m korvin setup` | Runs the guided setup again. It keeps your other settings. |
| `python -m korvin log` | Shows the last 20 entries of the sealed log. Add `--last 50` to see more. |
| `python -m korvin check` | Checks every seal in the log. Add `--seal VALUE` to compare a seal that you kept. |
| `python -m korvin server add NAME --risk read -- COMMAND` | Adds a local tool server. See "Local tool servers" below. |
| `python -m korvin server list` | Shows the tool servers, their risk levels, and their approved tools. |
| `python -m korvin server remove NAME` | Removes a tool server. |

The options `--model NAME` and `--folder PATH` still work. They replace the values in the settings for one session.

### The sealed log

Korvin adds one line to its log for each event.
It records the start and end of each session, each tool call, and each standing rule added or cleared.
It also records each removed turn and each full conversation.
A tool call line holds the tool, the short argument from the action line, the result, and the decision.
The decision says if a rule allowed the call, or if you said yes or no.
The log holds no file contents and no chat text.
It keeps up to 60 characters of each tool argument and of each standing rule.
That is enough for a file name, the start of a note, or the start of a tool server input, such as a search query.

Each line has a seal: a SHA-256 value that covers the line and the seal of the line before it.
`python -m korvin check` proves that no line was changed, removed, or inserted, unless someone rebuilt every seal after it.
A person who can write the file can rebuild all seals, or cut lines from the end.
To catch that, Korvin shows the last seal when a session ends. Keep it somewhere else, and check it later with `--seal`.

The log also records each tool server start, each approval, each changed tool, and the server of each tool call.

If Korvin cannot write the log, it tells you once, and the chat goes on without a record.

### Local tool servers

A tool server is a separate program that gives Korvin extra tools, such as web search.
Korvin speaks the Model Context Protocol (MCP), the common standard for such servers.
Korvin starts each server on this computer, and talks to it through the server's input and output.
Korvin itself still never connects to the internet.

To try it, add the example server in `examples\clock_server.py`. It tells the time and converts units.

1. Open a terminal in this folder.
2. Type `python -m korvin server add clock --risk read -- python C:\full\path\to\examples\clock_server.py`
3. Korvin starts the server and shows each tool, as the model will see it. Read each description.
4. Type `y` to approve the tools. Korvin stores the server in its settings.
5. Start the chat with `python -m korvin`, and ask for the time.

Korvin follows these rules:

- Only servers that you add can run. Korvin starts each one without a shell, and with a small environment.
- A server does not get your other environment variables, such as keys. To pass one, add `--env NAME` to the command.
- Never type a key in the server command. Korvin stores the command in its settings file.
- Each server has a risk level: `read` or `write`. Korvin 1.0 refuses servers that control other programs.
- Korvin keeps a SHA-256 fingerprint of each tool that you approve: its name, description, and input schema.
- If a tool changes or a new tool appears, Korvin shows what changed. The model never sees that tool until you approve it again.
- The model sees at most 8 server tools in total. Each description is cut to 300 characters.
- Korvin refuses a tool whose input schema points to another file or a web address.
- Korvin asks before every call of a server tool. The question shows the server, the tool, and the exact input.
- A server tool result is outside text, like a file. After it, the question before an unexpected read applies.
- Once outside text entered the request, Korvin asks again, even after "yes, for this session". The question says why.

Korvin controls which tools the model may call. It does not control what a server does inside.
A server that you install can use the internet by itself, or read your files. Add only servers that you trust.
Korvin understands both versions of the protocol: the new one (2026-07-28), and the older one with a handshake.

### Web search

The example server `examples\search_server.py` gives Korvin two tools: `search` and `fetch`.
`search` finds web pages. `fetch` reads one web page and returns its text, cut to 8,000 characters.
The server uses Ollama's hosted web search service, so it needs an Ollama account, an API key, and paid usage credits.

With this server, your search queries and the addresses that you fetch leave the computer and go to Ollama's service.
Korvin itself still sends nothing. The server is a separate program, and it talks only to `ollama.com`.

1. Make an account at https://ollama.com, and add usage credits. The account is free. Web search is not.
2. Create an API key at https://ollama.com/settings/keys.
3. Store the key in the environment variable `OLLAMA_API_KEY`. On Windows, type `setx OLLAMA_API_KEY "your-key"`.
4. Close the terminal, and open a new one in this folder. Only a new terminal sees the variable.
5. Type `python -m korvin server add web --risk read --env OLLAMA_API_KEY -- python C:\full\path\to\examples\search_server.py`
6. Read the two tools, and type `y` to approve them.

Never type the key in the server command. The `--env OLLAMA_API_KEY` part passes the key to this server only.
Before each call, Korvin shows the query or the address. Read it before you say yes.
A hidden order can try to put private text into a query or an address, and so send it away.
On 2026-11-24, a new account without usage credits got error 402 for `search` and for `fetch`. Ollama's reply said: "Add usage credits to use web search".
We did not buy credits, so we have not seen a search result from Ollama's service.

### Commands in the chat

| Command | What it does |
|---|---|
| `/help` | Shows the commands. |
| `/new` | Starts a new conversation. The standing rules stay. |
| `/rule TEXT` | Adds a standing rule, such as `/rule Answer in Spanish.` |
| `/rules` | Shows the standing rules. |
| `/rule clear` | Removes all standing rules. |
| `/exit` | Ends Korvin. |

Korvin keeps at most 5 standing rules of up to 200 characters each.
It sends them with every request until Korvin ends. Nothing from a file, a note, or the model can add a rule.

### Questions that Korvin asks

For each question, Enter alone means no.

| Question | When Korvin asks | Answers |
|---|---|---|
| Save this note? | Before every note, unless you allowed notes for the session. | `y` once, `s` for this session, `n` no |
| Read a file that you did not name? | A file or note entered the current request, and the model wants another file that you did not name. Such a read may come from an order hidden in that text. | `y` once, `s` all reads for this request, `n` no |
| Keep a standing rule? | Your message says "from now on", "in every answer", "always ...", or the Spanish words "a partir de ahora", "siempre", or "en cada respuesta". | `y` yes, `n` no |
| Approve these tools? | You add a tool server, or a server has a new or changed tool. | `y` yes, `n` no |
| Use the tool of a tool server? | Before every call of a server tool. | `y` once, `s` for this session, `n` no |

### Messages that Korvin shows

- "The conversation is 85% full." Korvin shows this after an answer, once the conversation passes 80% of the model's context.
- "The conversation is full." Korvin did not send the request, so the model never gets a cut conversation. Type `/new`.
- "Korvin removed this turn." A turn failed, so Korvin removed it. The model forgets that turn, and the files it read in it.
- A line that starts with `(model text) [tool]` is text from the model. Korvin's own action lines start with `  [tool]`.
- "Warning: the model runs ...% on the graphics card". Korvin checks this once, after the first answer. It warns if part of the model runs on the CPU, or if the context is below 65,536 tokens.
- "Last seal of the log". Korvin shows this when a session ends. See "The sealed log" above.
- "Server tools for the model". Korvin shows this at the start when you added a tool server. It names the approved tools.

## Run the tests

Type `python -m unittest discover -s tests` in this folder.
On 2026-11-24, 284 unit tests ran: 282 passed, and 2 were skipped. The tests use a fake model, so they need no real model.

## Folder map

| Path | Content |
|---|---|
| `korvin\` | The program. Thirteen small files, and each file has one job. |
| `korvin\first_run.py` | The guided setup. |
| `korvin\seal.py` | The sealed log, the check, and the list of entries. |
| `korvin\mcp.py` | The client for local tool servers. It is the only file that starts other programs. |
| `korvin\servers.py` | The approval of server tools, their fingerprints, their limits, and the `server` commands. |
| `examples\clock_server.py` | An example tool server: a clock and a unit converter. |
| `examples\search_server.py` | An example tool server: web search through Ollama's hosted service. It is not part of the `korvin` package. |
| `pyproject.toml` | The install file for `pip install .`. It lists no dependencies. |
| `tests\` | The tests. They use a fake model, so they need no real model. They include three small test servers and a fake of the web search service. |
| `evals\` | The evals. `evals\parcel_server.py` is the tool server of the eval family for tool servers. |
| `docs\DECISION_LOG.md` | Every important choice and its reasons, for readers who do not write code. |
| `docs\USER_GUIDE.md` | How to install, use, and remove Korvin, with the measured numbers. |
| `docs\EVAL_PLAN.md` | Every kind of eval, and the research behind it. |
| `docs\MODEL_NOTES.md` | What we know and measured about the model. |
| `docs\RESEARCH_NOTES.md` | The sources behind the design rules. |
| `docs\SECURITY_MAP.md` | Each safety control, linked to public security frameworks. |
| `docs\history\` | The first draft of the decision log, kept for history. |
| `korvin.example.json` | An example settings file. |
| `LICENSE`, `NOTICE` | The Apache 2.0 license, and the copyright notice. |

## Older versions

Two older versions of Korvin were never released.
This project does not reuse their code (D-001), and nothing here depends on them.

## License

Korvin is open source under the Apache License 2.0. The full text is in [LICENSE](LICENSE).
Copyright 2026 NosisTech. See [NOTICE](NOTICE).
Decision D-035 in the decision log explains why we chose this license.
