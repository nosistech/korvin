"""Guide the user through the first-run setup: find Ollama, choose a model, and choose a folder.

Korvin writes no file, and Ollama makes no model copy, until the user confirms the summary at the end.
For every yes-or-no question, Enter alone means no.
"""

import re

from korvin.chat import write_stdout
from korvin.config import CONTEXT_GOAL, ConfigError, check_folder, write_settings
from korvin.door import DoorError, ModelDoor
from korvin.gate import Reader, Writer, clean, said_yes

RECOMMENDED = "qwen3.5:2b-q4_K_M"
# Measured on a 4 GB RTX 3050 Ti: with num_ctx alone, 30% of the model ran on the CPU. With all three, none did.
COPY_PARAMETERS = {"num_ctx": CONTEXT_GOAL, "num_gpu": 999, "num_batch": 256}
YES_NO = "[y] yes   [n] no  (Enter = no)"
NO_OLLAMA = (
    "Step 1: Korvin looks for Ollama on this computer. {error}\n"
    "1. If Ollama is not installed, install it from https://ollama.com/download.\n"
    "2. Start Ollama: open the Ollama app, or type: ollama serve\n"
    "3. Then type: python -m korvin\n"
)
NO_MODELS = (
    "Ollama has no model yet. Download the model that Korvin is built for with this command:\n"
    f"    ollama pull {RECOMMENDED}\nThen type: python -m korvin\n"
)
SMALL_CONTEXT = (
    f"Korvin is built for a 64k context ({CONTEXT_GOAL:,} tokens), but this model is not set to that size.\n"
    "Korvin can ask Ollama for a copy named {copy} that uses 64k and keeps the model on the graphics card.\n"
    "Ollama makes the copy only after your last yes, at step 5.\n"
)
CUT_SHORT = "Long conversations will be cut short, because the model holds less text."
FOLDER_INTRO = (
    "Choose the folder that Korvin may read. Korvin can read every file inside it, without a question.\n"
    "It cannot read anything outside it. Type the full path, or press Enter for no folder.\n"
)
STOPPED = "Setup stopped. Korvin wrote no file, and Ollama made no copy.\n"


def run_setup(door: ModelDoor, settings_file: str, read_line: Reader = input, write: Writer = write_stdout) -> bool:
    """Run the guided setup. Return True if the user confirmed it and Korvin wrote the settings file."""
    write("Korvin setup: five short steps. Korvin changes nothing until you confirm the last one.\n")
    try:
        chosen = choose_model(door, read_line, write)
        folder = None if chosen is None else choose_folder(read_line, write)
    except (EOFError, KeyboardInterrupt):
        chosen = None
    if chosen is None or folder is None:
        write("\n" + STOPPED)
        return False
    (model, copy), shown = chosen, folder or "none (the file tools are off)"
    plan = f"  64k copy: {copy}, which Ollama makes after your yes\n" if copy else ""
    write(clean(f"Step 5: Summary\n  Model:  {model}\n{plan}  Folder: {shown}\n  Settings file: {settings_file}\n"))
    if not ask_yes(read_line, write, ("Make the copy and write" if copy else "Write") + " the settings file?"):
        write(STOPPED)
        return False
    try:
        model = make_copy(door, model, copy, write) if copy else model
        write_settings(settings_file, model=model, folder=folder or None)
    except (OSError, ConfigError) as error:
        write(clean(f"Korvin could not write the settings file: {error}\n"))
        return False
    write("Setup is done. You can run it again with: python -m korvin setup\n\n")
    return True


def choose_model(door: ModelDoor, read_line: Reader, write: Writer) -> tuple[str, str] | None:
    """Steps 1 to 3: check Ollama, let the user pick an installed model, and offer a 64k copy of it."""
    try:
        models = door.installed_models()
    except DoorError as error:
        write(clean(NO_OLLAMA.format(error=error)))
        return None
    if not models:
        write(NO_MODELS)
        return None
    write("Step 1: Ollama answers.\nStep 2: Choose a model. These models are installed:\n")
    facts = [model_facts(door, entry["name"]) for entry in models]
    for number, (entry, (tools, context)) in enumerate(zip(models, facts), 1):
        shown = f"{context:,}" if context else "not set (Ollama's default)"
        write(clean(f"  {number}. {entry['name']}  {size_text(entry.get('size'))}  tools: {tools}  context: {shown}\n"))
    choices = {str(number): number - 1 for number in range(1, len(models) + 1)}
    while (answer := read_line("number> ").strip()) not in choices:
        write(f"Type a number from 1 to {len(models)}.\n")
    name, (tools, context) = models[choices[answer]]["name"], facts[choices[answer]]
    if tools == "no":
        write("This model cannot use tools, so Korvin can only chat with it.\n")
    return offer_copy(name, context, read_line, write)


def model_facts(door: ModelDoor, name: str) -> tuple[str, int | None]:
    """Return whether the model can use tools ("yes", "no", or "unknown"), and the context size that it is set to."""
    try:
        facts = door.model_facts(name)
    except DoorError:
        return "unknown", None
    capabilities = facts.get("capabilities")
    tools = ("yes" if "tools" in capabilities else "no") if isinstance(capabilities, list) else "unknown"
    parameters = facts.get("parameters")
    found = re.search(r"^num_ctx\s+(\d+)\s*$", parameters, re.MULTILINE) if isinstance(parameters, str) else None
    return tools, int(found.group(1)) if found else None


def size_text(size: object) -> str:
    """Return a model size in bytes as a short text, such as "1.9 GB"."""
    return f"{size / 1e9:.1f} GB" if isinstance(size, int) and not isinstance(size, bool) else "size unknown"


def offer_copy(name: str, context: int | None, read_line: Reader, write: Writer) -> tuple[str, str]:
    """Step 3: if the model's context is below 64k, offer a 64k copy. Return the model, and the copy to make or ""."""
    if context and context >= CONTEXT_GOAL:
        write(f"Step 3: The model is set to a {context:,}-token context. Good.\n")
        return name, ""
    copy = "korvin-" + re.sub(r"[^A-Za-z0-9._-]", "-", name.removesuffix(":latest")) + "-64k"
    write(clean("Step 3: " + SMALL_CONTEXT.format(copy=copy)))
    if ask_yes(read_line, write, "Make the copy?"):
        return name, copy
    write(clean(f"Korvin will use {name}. {CUT_SHORT}\n"))
    return name, ""


def make_copy(door: ModelDoor, base: str, copy: str, write: Writer) -> str:
    """Ask Ollama for the 64k copy, after the last yes. Return the copy, or the base model if Ollama failed."""
    try:
        door.create_copy(copy, base, COPY_PARAMETERS)
    except (DoorError, KeyboardInterrupt) as error:
        reason = str(error) or "You pressed Ctrl+C."
        write(clean(f"Ollama could not make the copy. {reason}\nKorvin keeps {base} in the settings. {CUT_SHORT}\n"))
        return base
    write(clean(f"Ollama made the copy. Korvin will use {copy}.\n"))
    return copy


def choose_folder(read_line: Reader, write: Writer) -> str | None:
    """Step 4: ask for the folder that Korvin may read. Return its real path, or "" for no folder."""
    write("Step 4: " + FOLDER_INTRO)
    while True:
        answer = read_line("folder> ").strip().strip('"').strip()
        if not answer:
            return ""
        try:
            return str(check_folder(answer))
        except ConfigError as error:
            write(clean(f"{error}\n"))


def ask_yes(read_line: Reader, write: Writer, question: str) -> bool:
    """Ask a yes-or-no question. Return True only for "y" or "yes"."""
    write(f"{question}  {YES_NO}\n")
    return said_yes(read_line, write, "> ")
