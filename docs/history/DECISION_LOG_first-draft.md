# Korvin decision log

This document records every important choice in the Korvin project.
A reader who does not write code can follow each entry.
You do not need coding experience to read it.

## How to read an entry

Every entry has the same six parts, in the same order.

1. **The question.** What we had to decide.
2. **Why it matters.** What goes wrong if we choose badly.
3. **The options.** Every realistic alternative, with its good and bad points.
4. **The choice.** What we picked.
5. **The reasons.** Why this option won over the others.
6. **The cost.** What we give up by choosing it.

Each entry also has a status.

| Status | Meaning |
|---|---|
| Decided | The choice is final. We build on it. |
| Proposed | A recommendation exists. The project owner has not approved it yet. |
| Replaced | A later entry changed this choice. The entry stays for history. |

We never delete or rewrite an old entry.
If we change our mind, we add a new entry and mark the old one as Replaced.

This is the first draft. The current log is `docs\DECISION_LOG.md`.
On 2026-11-24, before the public release, we edited the wording of this draft.
A personal name became "the owner", and D-012 now describes the build method by its steps.
No decision, date, or number changed.

---

## D-001: Start a new, small Korvin

**Status:** Decided by the owner.

**The question.** Do we finish one of the older versions, or do we start again?

**Why it matters.** Korvin was "in development" from April to November 2026.
Two versions were built and neither was released.
A third long attempt would damage trust in the project.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Finish the Rust version | About 26,000 lines already exist. All tests pass. | It is large and hard to read. Its best feature needs a second private product. |
| B. Revive the first version | The public website already describes it. | It has many moving parts: Telegram, voice, a web dashboard, cloud models. |
| C. Start a new, small Korvin | We control the size from day one. Every part can be simple. | We leave working code behind. |

**The choice.** Option C. We start a new Korvin with a small, fixed scope.

**The reasons.**
The older versions failed for the same reason: the scope kept growing.
The first version added channels, voice, and eleven skills.
The Rust version added a desktop window, plug-in servers, and signed receipts.
A small scope with a written limit is the only option that removes this cause.

**The cost.** We do not reuse the older code.
We can still reuse its lessons, and each reuse needs its own entry in this log.

---

## D-002: Build in private, then publish as open source

**Status:** Decided by the owner.

**The question.** When does the public see the code?

**Why it matters.** Publishing unfinished code repeats the "in development" problem in public.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Public from the first day | Full transparency. | Visitors see an unfinished product again. |
| B. Private until release, then public | The first thing the public sees is a finished product. | No outside feedback during the build. |
| C. Private forever | Nobody can copy the work. | Nobody can audit it. This conflicts with the goal of an auditable tool. |

**The choice.** Option B.

**The reasons.** Korvin promises that anyone can read and check it.
That promise needs public code.
The promise is stronger when the first public version is complete and tested.

**The cost.** We get no outside review until release day.
We reduce this risk with tests and a written security checklist before release.

---

## D-003: One active folder, one deprecated folder

**Status:** Decided by the owner.

**The question.** Where do the Korvin files live on the computer?

**Why it matters.** Korvin was spread across four folders with similar names.
People and AI tools opened the wrong folder more than once.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Keep the four folders | No work needed. | The confusion continues. |
| B. Put the old versions inside the new folder | Truly one folder. | Old code sits next to new code. Searches and tools mix them. |
| C. One new folder, plus one clearly named folder for everything old | Old and new can never mix. | Two folders exist, not one. |

**The choice.** Option C.

- `Documents\Korvin` holds the new project and nothing else.
- `Documents\Korvin-deprecated` holds every older version, for reference only.

**The reasons.** The owner asked that the old Korvin must not interfere with the new one.
A separate folder gives the strongest separation.
The word "deprecated" in the name tells every reader that the content is retired.

**The cost.** Old notes still mention the former folder paths.
A table in `Korvin-deprecated\README.md` translates them.

---

## D-004: Keep this decision log from the first day

**Status:** Decided by the owner.

**The question.** How do we record why Korvin is built the way it is?

**Why it matters.** Without a record, nobody can tell a deliberate choice from an accident.
An auditor needs the reasons, not only the code.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. No log | No effort. | The reasons are lost. |
| B. A technical log for developers | Short to write. | Most readers cannot understand it. The old log reached 80,000 characters of jargon. |
| C. A log that anyone can read, with a fixed format | Anyone can read it. Every entry shows the alternatives. | Each entry takes more time to write. |

**The choice.** Option C, in this file.

**The reasons.** Korvin is for people who want to check their tools.
Many of them are not programmers.
A fixed six-part format also keeps every entry complete.

**The cost.** We write an entry before we build each important part. This slows the start of each step a little.

---

## D-005: The scope of Korvin 1.0

**Status:** Decided by the owner. Feature 4, the left-out list, and the size limit were later changed by D-007, D-008, and D-009.

**The question.** What does Korvin 1.0 do, and what does it refuse to do?

**Why it matters.** Scope growth stopped both older versions.
A written limit lets us say "no" and finish.

**The proposal.**
Korvin 1.0 is a private AI assistant that runs in a terminal window on your own computer.
It asks before it acts, and it keeps a record that you can check.

Korvin 1.0 does five things.

| # | Feature | What it means |
|---|---|---|
| 1 | Local chat | You talk to an AI model that runs on your own computer through Ollama. |
| 2 | Four safe tools | The model can list a folder, read a file, save a note, and find a note. |
| 3 | Ask first | Before any tool runs, Korvin shows the exact action. You approve or refuse it. |
| 4 | Local only | Korvin connects only to your own computer. It refuses every other address. |
| 5 | A record you can check | Korvin writes each step to a sealed log. One command proves that nobody changed it. |

Korvin 1.0 does not include these things.

| Left out | Reason |
|---|---|
| Voice | Large, hardware dependent, and already dropped once. |
| Telegram and other channels | Each channel is a new door to the internet. |
| Web dashboard or desktop window | A terminal is enough for version 1.0 and is far smaller. |
| Cloud models | They send your text to another company. This conflicts with feature 4. |
| Plug-ins, skills, and external tool servers | Each one adds code that we cannot audit. |
| The Nosis gateway | Korvin 1.0 must work alone. A link to Nosis can come later as its own decision. |

**The size limit.** The whole program stays under 1,500 lines of code, in seven small files.
Each file does one job.

**The build order.** Each step produces something that works.

1. Chat with a local model.
2. Add the four tools and the "ask first" rule.
3. Add the sealed log and the check command.
4. Add tests, the user guide, and the security notes.
5. Release version 1.0 and update the websites.

**The cost.** Korvin 1.0 looks modest next to large assistants.
That is deliberate. Small is the feature.

---

## D-006: The programming language

**Status:** Decided by the owner. Python, with no added packages.

**The question.** Which programming language do we write Korvin in?

**Why it matters.** The language decides how easy the code is to read, to audit, to install, and to finish.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Python, with no added packages | Reads almost like English. Everything Korvin needs is built in. No outside code to trust. | The user must have Python installed. It is slower, but Korvin waits on the model, not on itself. |
| B. Go | Produces one program file that needs no installation. Simple and safe. | Less readable for non-programmers. Go is not installed on the build computer today. |
| C. Rust | The strongest safety guarantees. | Hard to read. Slow to write. Needs many outside packages. The second Korvin used Rust and stalled. |
| D. TypeScript | Very popular. | Normal projects pull in hundreds of outside packages. Hard to audit. |
| E. One web page, like Bunker | Nothing to install. | A web page cannot safely read files or keep a sealed log. Too limited for an agent. |

**The recommendation.** Option A: Python, using only what ships with Python.

**The reasons.**

1. **Readable.** A person without coding experience can follow Python line by line.
2. **Nothing to trust but Python itself.** Korvin adds zero outside packages. This removes the risk of a poisoned package.
3. **Everything is built in.** Web requests, the database, and the sealing math all ship with Python.
4. **Fast to finish.** The whole program is small enough to build and test in days.
5. **Easy to check.** An auditor can read 1,500 lines in one sitting.

**The cost.** Users install Python first, which takes a few minutes.
Go remains the fallback if a single program file becomes a firm requirement.

---

## D-007: Add local tool servers (MCP)

**Status:** Decided. The owner asked for the feature. The safety rules below are the proposed design.

**The question.** Can Korvin use extra tools that other people wrote?

**Why it matters.** MCP is the common standard for giving tools to an AI assistant.
Thousands of ready-made tool servers exist.
Each server is also a separate program that Korvin did not write and cannot fully control.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. No MCP | Smallest and safest. | Korvin can only do four things. It looks dated. |
| B. Local MCP servers only | Korvin gains many tools. The servers run on your computer, where you can see them. | Each server is extra code that you must trust. |
| C. Local and internet MCP servers | The widest choice of tools. | Internet servers are a new door that sends data away. Sign-in adds much code. |

**The choice.** Option B. Korvin 1.0 runs MCP servers as local programs on your own computer.

**The safety rules.**

1. No server runs unless you list it in the settings file.
2. Every tool from a server passes the same "ask first" rule as the built-in tools.
3. Korvin treats everything a tool returns as untrusted text, never as an order.
4. The sealed log records every tool call and its server.

**The reasons.** MCP gives Korvin current abilities without growing Korvin itself.
The local-only limit keeps the design honest and small.

**The cost.** Korvin cannot stop a server that you installed from using the internet by itself.
Korvin controls which tools the model may call. It does not control what the server does inside.
The user guide must say this clearly.
This replaces the "plug-ins and external tool servers" line in the left-out list of D-005.

---

## D-008: Web search comes through a tool server, not through Korvin

**Status:** Decided. The owner asked for the feature. The design below is proposed.

**The question.** How does Korvin search the web?

**Why it matters.** Web search needs the internet.
Web pages can also contain hidden instructions that try to trick the model.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. No web search | Fully offline. | The assistant cannot answer questions about current events. |
| B. Build web search into Korvin | Works out of the box. | Korvin itself opens a door to the internet. Search websites change often, so the code breaks. |
| C. Use a search tool server through MCP | Korvin stays offline. You choose the search service. You can remove it in one line. | You must install one search server. |

**The choice.** Option C.

**The reasons.** Korvin's own code never touches the internet for search.
The search server is a separate, visible program that you chose.
The "ask first" rule shows you each search before it runs.

**The cost.** Web search does not work until you add a search server.
The user guide will include one tested example.

---

## D-009: Other companies' models are allowed, but only when you switch them on

**Status:** Decided. The owner asked for the feature. The safety rules below are the proposed design.

**The question.** Can Korvin use models from companies such as Anthropic (Claude) or DeepSeek?

**Why it matters.** A small model on a laptop is private but limited.
A large hosted model is stronger, but your text leaves your computer.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Local models only | Nothing ever leaves the computer. | Weak hardware gives weak answers. |
| B. Local by default, hosted models as a clear opt-in | You choose per session. Private work stays private. | Korvin needs a second kind of door. |
| C. Hosted models by default | Best answers with no setup. | Private by accident is impossible. This conflicts with the purpose of Korvin. |

**The choice.** Option B.

**The safety rules.**

1. A new Korvin talks only to your own computer.
2. A hosted model works only after you add its company to the settings file by name.
3. Korvin shows a clear warning on screen during every session that uses a hosted model.
4. Secret keys come from the computer's environment. Korvin never writes them to a file or to the log.
5. The sealed log records which model and which company answered each turn.
6. One file holds all model connections. A test fails if any other file opens a network connection.

**The reasons.** The user decides, and the decision is always visible.
This changes feature 4 of D-005 from "local only" to "local by default".

**The cost.** The program grows.
The size limit of D-005 rises from 1,500 to 2,500 lines, and from seven files to about ten.
This is the last planned increase for version 1.0.

---

## D-010: Two kinds of checks: tests and evals

**Status:** Decided. The owner asked for evals. The design below is proposed.

**The question.** How do we know that Korvin works and stays safe?

**Why it matters.** An AI assistant can fail in two ways.
The program can have a bug, or the model can behave badly.
One kind of check cannot catch both.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Manual checks only | No effort now. | Slow, and nobody repeats them. |
| B. Tests only | Fast, free, and exact. | Tests use a fake model. They cannot show how a real model behaves. |
| C. Tests and evals | Covers the program and the real model. | Evals take minutes to run. Evals on hosted models cost a little money. |

**The choice.** Option C.

- **Tests** check the program with a fake model. They run in seconds and must always pass.
- **Evals** give real tasks to a real model and score the result as pass or fail.

**The first evals.**

| Eval | What it proves |
|---|---|
| Answer a simple question | The chat works from start to end. |
| Read a file and summarize it | The model uses the right tool. |
| Save a note, then find it | Memory works across steps. |
| Ask for a file outside the allowed folder | Korvin refuses. |
| Read a file that contains a hidden order | Korvin does not obey text inside a file. |
| Refuse a tool at the "ask first" prompt | Nothing runs after a "no". |
| Change one line of the sealed log | The check command reports the change. |

**The reasons.** Safety claims need proof that anyone can run again.
Each release will publish its eval results for each tested model.

**The cost.** We write each eval before we call a feature finished.

---

## D-011: Which model companies Korvin supports, and how you pay for them

**Status:** Decided by the owner.

**The question.** Which hosted models does Korvin 1.0 support, and can a monthly subscription pay for them?

**Why it matters.** Every extra company is extra code to write, test, and keep working.
Subscriptions and programs also follow different rules, and breaking those rules can close an account.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Any company | The most choice. | Endless testing. Many services behave a little differently. |
| B. The three largest companies, plus local models | Covers what most people use. A short list that we can test fully. | Smaller companies are left out for now. |
| C. One company only | The least code. | Lock-in. This conflicts with the purpose of Korvin. |

**The choice.** Option B.

| Model source | Supported in 1.0 | How Korvin connects |
|---|---|---|
| Local models through Ollama | Yes, and this is the default | Directly, on your own computer |
| Claude (Anthropic) | Yes, as an opt-in | The official Anthropic package, installed only by people who want Claude |
| ChatGPT models (OpenAI) | Yes, as an opt-in | A direct connection with a secret key |
| Gemini (Google) | Yes, as an opt-in | A direct connection with a secret key |
| Other companies | No | A later decision |

**What is allowed and what is not.**

A subscription and a developer account are two different products.

| Way to pay | What it is for | Can Korvin use it? |
|---|---|---|
| A monthly subscription (Claude, ChatGPT, or Gemini app) | The company's own apps | No. The companies do not let outside programs sign in with a subscription. |
| A developer account with a secret key | Your own programs, such as Korvin | Yes. You pay for what you use. Google also offers a free level with limits. |
| A local model | Your own computer | Yes. It is free and private. |

**The reasons.** Korvin follows each company's rules, so no user risks an account.
The secret-key route is the route the companies built for programs like Korvin.

**The cost.** A subscription that you already pay for does not cover Korvin.
Small developer-account costs apply when you use a hosted model.
We will check each company's current terms again before release, because they change.
DeepSeek, named as an example in D-009, is not in version 1.0.

---

## D-012: How we build Korvin: plan, write, review

**Status:** Decided by the owner.

**The question.** How do we build Korvin, and who checks the work?

**Why it matters.** Code that the same author writes and approves gets less scrutiny.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Write and approve in one pass | Simple. | Nobody independent reviews the work. |
| B. Separate steps: plan, write, review | Every part gets a second look. | Each step needs a written brief. |

**The choice.** Option B.

1. **Plan.** A written brief says what to change and how to test it.
2. **Write.** The code is written from the brief.
3. **Review.** A separate review reads the code, and runs the tests and evals.

The owner approves each decision and each release.

**The reasons.** A written brief forces a clear plan before any code exists.
An independent review catches mistakes that an author misses.

**The cost.** Each step takes a little longer.

---

## D-013: The full feature map: now, later, and never

**Status:** Decided. The map below is the proposed design.

**The question.** A top assistant can have dozens of features. Which ones does Korvin need?

**Why it matters.** Without a map, each good idea becomes a reason to delay the release.

**The map.**

| Feature | Verdict | Reason |
|---|---|---|
| Chat with answers that appear as they are written | Version 1.0 | The base of everything. |
| Four built-in file and note tools | Version 1.0 | See D-005. |
| The "ask first" rule | Version 1.0 | The main safety control. |
| The sealed log and the check command | Version 1.0 | The proof. |
| Local tool servers (MCP) | Version 1.0 | See D-007. |
| Web search through a tool server | Version 1.0 | See D-008. |
| Hosted models as an opt-in | Version 1.0 | See D-009 and D-011. |
| Tests and evals | Version 1.0 | See D-010. |
| Save a conversation and continue it later | Version 1.1 | Useful, but not needed to prove the product. |
| Two-model mode: a strong model plans, a second model does the steps | Version 1.1 | The owner asked for it. It builds on the hosted-model work in 1.0. |
| Skills: folders of written instructions | Version 1.1 | Simple, but each skill needs its own safety review. |
| Shortening very long conversations automatically | Version 1.1 | Needed only for long sessions. |
| Images as input | Later | Depends on the model. |
| Running commands on your computer | Later, with strong limits | The most dangerous tool. It needs a separate safety design. |
| A window or web page | Later | A terminal is enough to release. |
| Voice | Later | Large and hardware dependent. |
| Chat apps such as Telegram | Not planned | Each one is a permanent door to the internet. |
| Acting without asking | Never | This removes the main safety control. |

**The rule.** Version 1.0 has eight features and no more.
A new idea goes to the "Version 1.1" or "Later" rows, with a new entry in this log.

**The cost.** Korvin 1.0 will not match the feature lists of large assistants.
It will be finished, safe, and understandable, which the older versions never were.


---

## D-014: Design rules that come from real user complaints

**Status:** Decided by the owner.

**The question.** How should Korvin look and behave, so that people find it easy and safe?

**Why it matters.** The owner asked for research before design.
Complaints from real users show where other assistants fail.

**What the research found.** The sources are listed in `docs\RESEARCH_NOTES.md`.

| # | Finding | Where it comes from |
|---|---|---|
| 1 | People approve almost every permission question without reading. One report says about 93 percent. | Reports on coding assistants, and two research papers |
| 2 | A popular open assistant left a control port open by default. Researchers found many thousands of exposed copies. | Security reports on OpenClaw, early 2026 |
| 3 | Its public skill store contained hundreds of harmful skills. | The same reports |
| 4 | A tool server can hide orders inside the description of a tool. It can also change a tool after you approved it. | Research on MCP security |
| 5 | Several assistants write files or switch on usage tracking before the user chooses anything. | A review of nine assistants, August 2026 |
| 6 | In some assistants, pressing Enter accepts the risky answer. | The same review |
| 7 | Small local models often make mistakes when they use tools. The model family matters more than the size. | Developer tests and forum reports |
| 8 | Assistants say "done" when they did not do the work. | Developer discussions |
| 9 | Setup difficulty is the most common complaint in reviews. A terminal stops many non-technical people. | Review studies and beginner guides |

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Ask before every tool, as D-005 says | Simple rule. | Finding 1 shows that people stop reading. The rule then protects nobody. |
| B. Never ask | No interruptions. | No safety. |
| C. Ask only when it matters, and make each question clear | People read rare, clear questions. | The rules need more care to design. |

**The choice.** Option C, with these twelve rules.

*Asking for permission*

1. Reading inside your chosen folder needs no question. Korvin shows the action and records it.
2. Saving a note, and every tool from a tool server, needs your approval.
3. Each question says clearly what will happen, not only the technical command.
4. You can answer "yes, once", "yes, for this session", or "no".
5. Pressing Enter alone always means "no".

*Staying closed*

6. Korvin never opens a port. No other device can connect to it.
7. Korvin has no skill store and never downloads tools by itself.
8. Korvin remembers the description of each approved tool. If a description changes, Korvin stops and asks again.
9. Korvin collects no usage data, and it writes no file before you finish the first-run setup.

*Being honest and easy*

10. The first run is a short guided setup. It finds your local models and lets you pick one. You edit no file.
11. Korvin shows what each tool really returned. It marks every failed or refused action clearly.
12. A session with a hosted model shows how much text went out, so the cost is never a surprise.

**The reasons.** Each rule answers one finding in the table.
Rules 1 to 5 replace the "ask before any tool" rule of D-005.
Fewer and clearer questions give more real safety than many ignored questions.

**The cost.** Korvin reads files inside your chosen folder without a question.
You must choose that folder with care. The first-run setup will say so.

---

## D-015: How people install Korvin

**Status:** Decided by the owner.

**The question.** What must a new user do to get Korvin running?

**Why it matters.** Finding 9 of D-014 says that setup is the top complaint.
An installer that Windows does not trust also frightens users with warnings.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. One command for people who have Python | Simple and honest. Nothing hidden. Works on Windows, Mac, and Linux. | The user needs Python and one line in a terminal. |
| B. A double-click Windows installer | The easiest for non-technical people. | Windows shows warnings unless we buy a signing certificate each year. Each release needs extra work. |
| C. Both, in two steps | Version 1.0 ships fast. The easy installer follows. | Non-technical users wait for version 1.1. |

**The choice.** Option C.

- **Version 1.0:** one install command, then the guided first-run setup. The guide shows each step with pictures.
- **Version 1.1:** a signed double-click installer for Windows.

**The reasons.** Version 1.0 users already run a local model, so one command is easy for them.
A signed installer costs money and time, so it must not delay the first release.

**The cost.** Version 1.0 is easy for technical users, and only acceptable for everyone else.
The website must say this honestly.

---

## D-016: Weak models get few tools, and only proven models get risky tools

**Status:** Replaced by D-017. The owner judged this design as too complex.

**The question.** Which models may use which tools?

**Why it matters.** A small local model makes more mistakes and is easier to trick.
A mistake while reading a file is harmless. A mistake while clicking in a browser can cost money.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Every model may use every tool | Simple. | A weak model can click the wrong thing. The user carries all the risk. |
| B. The user decides for each model | Flexible. | Most users cannot judge how capable a model is. |
| C. Korvin matches tool risk to proven model ability | Safe by default. Based on test results, not on promises. | A new model gets few tools until we test it. |

**The choice.** Option C.

**Three levels of tool risk.**

| Level | What the tools do | Examples |
|---|---|---|
| 1. Read | Look at information. Change nothing. | List a folder, read a file, find a note, search the web, read a web page |
| 2. Write | Change something small and private. | Save a note |
| 3. Control | Act in the outside world or in other programs. | Click and type in a browser |

**Three levels of model.**

| Model level | Which models | Tools allowed |
|---|---|---|
| Unknown | Any model that we have not tested | Chat only. No tools. |
| Basic | Models that pass the Level 1 and Level 2 evals, such as a tested small local model | Level 1 and Level 2 |
| Advanced | Models that also pass the Level 3 evals. We expect only strong hosted models here. | All three levels |

**The rules.**

1. Korvin ships with a short list of tested models and the level of each one.
2. A model enters a level only by passing the evals for that level. The results are published.
3. A model that is not on the list starts as "Unknown".
4. You must give each tool server a risk level when you add it. A server with no level counts as Level 3.
5. Korvin does not trust the risk labels that a tool server gives itself.
6. Level 3 tools ask before every single action. "Yes, for this session" is not offered.
7. Version 1.0 has no switch to skip these rules.
8. Control of the whole laptop is not part of version 1.0. It needs its own entry in this log.

**What this means for version 1.0.**

| Ability | Version 1.0 |
|---|---|
| Web search and reading web pages | Yes, for Basic and Advanced models |
| Browser control | Yes, for Advanced models only, with a question before every action |
| Laptop control | No. Later. |

**The reasons.** The guardrail rests on measured results, so anyone can check it.
A weak model can never reach a dangerous tool by accident.
Rule 7 keeps the promise simple: no hidden switch weakens it.

**The cost.** A new or unusual model works as chat only until someone tests it.
Hosted models need a developer account with a secret key, as D-011 explains.
A monthly subscription does not unlock the Advanced level.

---

## D-017: A simpler guardrail: local models get basic tools, the three big companies get all tools

**Status:** Decided by the owner. This entry replaces D-016.

**The question.** D-016 gave every model a level that it had to earn through tests. Is that too much?

**Why it matters.** The owner judged D-016 as over-engineered.
He will test one local model, his own Qwen, and not a long list of models.
A rule that needs a test programme for every model would delay the release.

**What the research found.** The sources are in `docs\RESEARCH_NOTES.md`.

| # | Finding | Strength of the evidence |
|---|---|---|
| 1 | Local models of about 4 billion parameters are the smallest that use tools reliably in general work. | Several blog tests agree. No official ranking confirms it. |
| 2 | Size alone is a weak guide. One very small model beat a larger one in a tool test. | One open benchmark of 21 models. |
| 3 | Qwen 3.5 at 2 billion parameters scores clearly lower than the 4 and 9 billion versions on general ability. | One independent analysis. |
| 4 | Every model can be tricked by hidden instructions, including the largest ones. Model size does not predict resistance. | Several studies, one with 42 models. |
| 5 | The strongest hosted models, with their safeguards, are tricked far less often. | Company reports and one 13-model study. |

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Keep D-016: every model earns a level through tests | Precise. | Needs a test programme for each model. Too heavy for this project. |
| B. Set a minimum model size for tools | One number. | Finding 2 shows that size is a weak guide. Korvin also cannot reliably read the size of a model. |
| C. Two groups, by where the model runs | One simple rule. Easy to explain and to check. | Coarse. A strong local model gets the same limits as a weak one. |

**The choice.** Option C.

| Model group | Which models | Tools allowed |
|---|---|---|
| Local | Every model that runs on your own computer | Read and Write tools: the four built-in tools, web search, and reading web pages |
| Hosted | Claude (Anthropic), ChatGPT models (OpenAI), and Gemini (Google) | All tools, including browser control |

**The rules.**

1. Korvin's code enforces the two groups. The model cannot change its own group.
2. Browser control asks before every single action. "Yes, for this session" is not offered for it.
3. You give each tool server a risk level when you add it. A server with no level counts as Control.
4. Korvin does not trust the risk labels that a tool server gives itself.
5. Version 1.0 has no switch to skip these rules.
6. Control of the whole laptop is not part of version 1.0.
7. The permission questions stay for every model, because finding 4 shows that no model is immune.

**The advice we give users.** Use a local model of about 4 billion parameters or more for tools.
We test Korvin with Qwen 3.5 at 2 billion parameters and publish the results honestly.
If that model fails the tool evals, the user guide will say so and will recommend the larger size.

**The reasons.** The rule fits in one sentence, so every user can understand it.
A local model can never reach a tool that acts in the outside world.
The hosted group has three names, which matches D-011.

**The cost.** A capable local model cannot control a browser in version 1.0.
A hosted model is not proof of safety. The questions before each action remain the real protection.

---

## D-018: The purpose of Korvin: a reference build and a teaching series

**Status:** Decided by the owner.

**The question.** Why do we build Korvin, when larger assistants already exist?

**Why it matters.** The purpose decides what "finished" means.
Without a clear purpose, the scope grows again.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. A product that competes with the large assistants | A big goal. | We cannot win on features. This goal stopped both older versions. |
| B. A reference build: working proof of a safe, governed assistant | Fits the NosisTech work in AI governance and AI security. Small enough for anyone to audit. | Modest. It will not attract many everyday users. |
| C. A step-by-step teaching series | Fits the NosisTech website, which already has build series. | Each step needs an article. |
| D. Stop the project | No more cost. | The work and the lessons are lost. |

**The choice.** Options B and C together.

Korvin is the simplest useful AI assistant for a small local model, built in the safest way we know.
Each build step also becomes one article.

**What this changes.**

1. The pitch is "a small assistant that you can read and check". It is not "a top assistant".
2. Clear code and clear reasons matter more than features.
3. Korvin maps each safety control to public security frameworks. The map is in `docs\SECURITY_MAP.md`.
4. The map uses four frameworks. Two come from OWASP: the Top 10 for LLM Applications and the Top 10 for Agentic Applications. The other two are MITRE ATLAS and the NIST AI Risk Management Framework.
5. The test model is Qwen 3.5 at 2 billion parameters, with a 64k context, on a 4 GB laptop graphics card.

**The reasons.** Nobody can audit a large assistant. Anybody can audit Korvin.
That is the one quality that larger products cannot copy.
A finished, modest Korvin also serves NosisTech better than an unfinished, ambitious one.

**The cost.** Korvin will have few everyday users, and that is accepted.

---

## D-019: A smaller version 1.0: local only

**Status:** Decided by the owner.

**The question.** With the purpose of D-018, what is the smallest version 1.0 that is still useful?

**Why it matters.** The owner asked for the simplest useful assistant.
Each feature that we remove makes the code easier to read, to audit, and to teach.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. Keep the plan: local models, hosted models, and browser control | The most abilities. | Two kinds of network door. The "local only" promise becomes "local by default". More code and more risk. |
| B. Local only in version 1.0 | The strongest and simplest promise: nothing leaves your computer. One door. | No strong hosted model, so no browser control. |
| C. Local only, and no tool servers either | The smallest. | No web search. Korvin also loses its best lesson, which is how to use outside tools safely. |

**The proposal.** Option B.

| Feature | Version 1.0 | Version 1.1 |
|---|---|---|
| Chat with a local model | Yes | |
| Four built-in tools, inside one chosen folder | Yes | |
| Permission questions | Yes | |
| Sealed log and check command | Yes | |
| Local tool servers, with web search as the tested example | Yes | |
| Guided first-run setup | Yes | |
| Tests, evals, user guide, security map | Yes | |
| Hosted models: Claude, ChatGPT, Gemini | | Yes |
| Browser control, for hosted models only | | Yes |
| Two-model mode | | Yes |

**The reasons.** A local-only program can make one absolute promise, and a test can prove it.
The series stays focused on one question: how to make a small local model useful and safe.
Hosted models then become a clean second series.

**The cost.** Version 1.0 is limited by the ability of a small model.
This moves the hosted part of D-009, D-011, and D-017 to version 1.1. Their rules stay valid.

---

## D-020: Build the best agent for one model, and prove it with measurements

**Status:** Decided by the owner.

**The question.** Should Korvin aim to be the best possible agent for one specific small model?

**Why it matters.** Large assistants are built for strong models.
Nobody publishes careful measurements of what a 2 billion parameter model can do safely on a normal laptop.
A goal without measurements would repeat the mistakes of the older versions.

**The options.**

| Option | Good points | Bad points |
|---|---|---|
| A. A general assistant for any model | Wide use. | Nothing special. We cannot test every model. |
| B. The best agent for one model, judged by features | Focused. | "Best" stays an opinion. |
| C. The best agent for one model, judged by a measured score | Focused and provable. The limits of the model become useful knowledge. | The result may show a low ceiling. Some tuning will not carry over to other models. |

**The choice.** Option C.

**The fixed conditions.**

1. The model is Qwen 3.5 at 2 billion parameters, under the Ollama name `qwen`.
2. The context is 64k (65,536 tokens). This is not negotiable. Tools need that much room to be useful.
3. The model runs fully on the 4 GB graphics card, with no spill into normal memory.
4. Every eval run records the context size and stops if it is below 64k.

**The method.**

1. We build the evals first. Each eval is a small task with a pass or fail check that a program decides.
2. Each task runs several times, because a small model gives different results on each run.
3. We record the baseline score before any tuning.
4. We test one change at a time. We keep a change only if the score rises.
5. Version 1.0 has at most five tuning experiments. Each one gets an entry in this log, with its numbers.

**Finding the thresholds.** The owner pointed out that a known limit is valuable.
The evals therefore measure how many steps the model can chain, for each kind of task.

| Kind of task | What we measure |
|---|---|
| Reading files in a chain | The longest chain that still succeeds most of the time |
| Saving several notes | The largest number that still succeeds |
| Mixed tasks, such as read and then save | The longest mix that still succeeds |
| Refusals and trick attempts | How often the model stays honest and safe |

Korvin can then work inside these limits on purpose, and tell the user when a task is beyond them.

**The new build order.**

| Step | Content |
|---|---|
| 3 | Evals and the baseline score |
| 4 | Up to five tuning experiments |
| 5 | The sealed log and the check command |
| 6 | Local tool servers, with web search |
| 7 | Guided setup, user guide, and a check of the security map |
| 8 | Release 1.0 |

**The reasons.** A measured limit is knowledge that others can use and check.
A program decides each pass or fail, so nobody has to trust our opinion.

**The cost.** The published numbers may be modest.
The tuning fits one model. The evals stay valid for any model, so a later model can be tested fast.
