# Security policy

Korvin is version 0.3.0. No third party has audited it.
The file `docs/SECURITY_MAP.md` lists each safety control, its tests, and the risks that Korvin does not solve.

## Supported versions

| Version | Supported |
|---|---|
| 0.3.0 | Yes |
| Older versions | No |

## How to report a problem privately

Please do not report a security problem in a public issue.
Use a private security advisory on GitHub instead.

1. Open the Korvin repository on GitHub.
2. Select the **Security** tab.
3. Select **Report a vulnerability**. GitHub opens a private form.
4. Describe the problem, and the steps that show it.
5. Name the Korvin version, the model, and your operating system.

Only you and the maintainers can see the report.
Korvin is a small project with no paid security team. We answer as soon as we can.

## What is in scope

A problem is in scope when Korvin breaks one of its own promises.

| Area | Example of a problem |
|---|---|
| Permission questions | Korvin saves a note or calls a server tool without a "yes". Enter alone counts as a "yes". |
| The read question | After outside text entered a request, Korvin reads a file that you did not name, with no question. |
| Folder containment | A file tool reads or lists something outside the folder that you chose. |
| The network door | Korvin's own process connects to an address outside this computer, or listens for other devices. |
| Tool servers | A new or changed tool reaches the model without your approval. A server gets an environment value that you did not pass with `--env`. |
| The sealed log | The check command misses a changed, removed, or inserted line, and the seals were not rebuilt. |
| Setup | Korvin writes a file, or Ollama makes a copy, before the last "yes" of the setup. |
| The example servers | A bug in `examples/` leaks the API key, or sends data to an address other than the documented one. |

## What is out of scope

These limits are known and documented. The section "What Korvin does not solve" in `docs/SECURITY_MAP.md` explains each one.

| Limit | Why it is out of scope |
|---|---|
| A hidden order makes the model say a given word, or refuse your task. | No question can stop words. The final eval run measured 7 of 200 such attacks. |
| The model states false facts. | A 2B model makes mistakes. The action lines show what really happened. |
| A tool server that you installed misbehaves. | A server runs with your rights. Korvin controls only which tools the model may call. |
| Someone with write access to your files rebuilds every seal. | Only a seal that you keep elsewhere shows this change. |
| Problems in Ollama or in the model itself. | Please report these to their makers. |
