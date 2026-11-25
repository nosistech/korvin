# Contributing to Korvin

Thank you for your interest in Korvin.
Korvin is small on purpose, so please read these rules before you open a pull request.

## Run the unit tests

The tests use a fake model. They need no real model and no network.

1. Install Python 3.11 or later.
2. Open a terminal in the project folder.
3. Type `python -m unittest discover -s tests`.

Every test must pass before a pull request can merge.

## The one-door rule

Only one file in the `korvin` package may reach the network: `korvin/door.py`.
Only `korvin/mcp.py` may start other programs, to run the tool servers that the user added.
Only `korvin/tools.py`, `korvin/config.py`, and `korvin/seal.py` may read or write files.
The test file `tests/test_one_door.py` checks these rules, and it fails if a change breaks one.

## Standard library only

Korvin uses only what ships with Python. Please add no outside package.
Zero outside packages means that there is no outside code to trust (D-004).
The `korvin` package also stays under 5,000 lines (D-026). The same test file checks this limit.

## The measured-change rule

A change to the behavior of the model needs a control run.
Examples are a new prompt sentence, a new tool, or a new sampling value.

1. Run the evals that the change targets, and some guard evals, without the change.
2. Run the same evals, with the same model and settings, with the change.
3. Compare both runs. `python -m evals --compare A.json B.json` puts them side by side.
4. Keep the change only if the gain on the target is statistically clear, and no guard gets worse.

The section "How we ran the tuning experiments of D-008" in `docs/DECISION_LOG.md` gives the full method.
`evals/README.md` explains how to run the evals. They need Ollama and the model.

A bug fix that does not change the model's input needs only its unit tests.

## Decisions

Korvin records every important choice in `docs/DECISION_LOG.md`, for readers who do not write code.
A large change needs a new entry there, with the options, the choice, the reasons, and the cost.
