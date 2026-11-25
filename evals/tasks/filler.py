"""Make long filler text for the long-context evals.

The text is invented prose about invented people, places, and numbers.
A seed makes it the same on every run, so two runs read the same files.
It never repeats one sentence, because a repeated sentence tests nothing.
It holds no real place, no code word in capital letters, no order, and none of the words that the probes use.
"""

import random

ONSETS = ("b", "br", "d", "dr", "f", "g", "gr", "h", "k", "l", "m", "n", "p", "r", "s", "st", "t", "th", "v", "w")
VOWELS = ("a", "e", "i", "o", "u", "ae", "ei", "ou")
CODAS = ("", "n", "r", "l", "m", "s", "th", "nd", "rk", "sk")
PLACE_ENDS = ("holm", "mere", "wick", "dun", "stead", "ford", "brook", "moor", "gate", "vale")
JOBS = ("baker", "ferryman", "weaver", "clerk", "miller", "glassblower", "surveyor", "shepherd", "tanner", "cooper",
        "potter", "beekeeper", "rope maker", "bookbinder", "carter", "fisher", "mason", "dyer")
THINGS = ("barrels", "baskets", "copper pots", "wool bales", "clay jars", "oak planks", "sacks of rye", "iron nails",
          "candles", "fishing nets", "goat hides", "salt blocks", "ledgers", "glass beads", "wheel rims")
BUILDINGS = ("granary", "chapel", "toll house", "mill", "boathouse", "market hall", "schoolhouse", "inn", "bridge",
             "watchtower", "tannery", "bathhouse", "warehouse", "orchard wall")
FEATURES = ("river bend", "north ridge", "salt marsh", "old quarry", "pine forest", "stone causeway", "east meadow",
            "harbour mouth", "beech grove", "dry valley")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
WEATHER = ("a cold wind", "steady rain", "a late frost", "thick fog", "a dry spell", "heavy snow", "a mild thaw")
TEMPLATES = (
    "{person}, a {job} from {place}, kept {n} {things} in a shed behind the {building}.",
    "In {month} of {year}, the council of {place} voted to repair the {building} near the {feature}.",
    "The road from {place} to {place2} crossed the {feature} and took {small} days on foot.",
    "{person} bought {n} {things} from {person2} and paid {price} silver marks for them.",
    "Every autumn the {job}s of {place} met at the {building} to settle their accounts.",
    "{weather} kept the boats of {place} in the harbour for {small} weeks in {month}.",
    "The {building} of {place} had {small} doors, and only one of them faced the {feature}.",
    "{person} wrote that the harvest near the {feature} gave {n} {things} in {year}.",
    "A {job} named {person} moved from {place} to {place2} after the flood of {year}.",
    "The market in {place} opened at dawn, and {person2} always arrived first with {things}.",
    "Records from {year} show that {place} counted {big} people and {n} working mills.",
    "{person} and {person2} argued for {small} years about the boundary at the {feature}.",
    "The old {building} in {place} was painted {colour} in {year} and again in {year2}.",
    "Travellers said that the inn at {place} served fish soup with {spice} on market days.",
    "During {weather} in {month}, {person} lost {n} {things} on the way to {place2}.",
    "The guild of {job}s in {place} had {small} rules, and the third rule was about {things}.",
    "From the {building} one could see the {feature} and, on clear days, the roofs of {place2}.",
    "{person} taught {small} children to read in the {building} of {place} each winter.",
    "A ledger from {place} lists {n} {things} sold to {place2} at {price} marks each.",
    "The bell of the {building} in {place} cracked in {year} and was recast by {person}.",
    "People in {place} believed that {weather} in {month} meant a good year for {things}.",
    "{person2} kept a diary about the {feature}, and it filled {small} thick books.",
    "The ferry between {place} and {place2} carried {n} {things} on its busiest day.",
    "When {person} retired, the {job}s of {place} gave a dinner in the {building}.",
    "Near the {feature} stood {small} stone markers, each carved with the name of a {job}.",
    "The price of {things} in {place} rose to {price} marks after {weather} in {year}.",
)
COLOURS = ("ochre", "pale blue", "dark green", "grey", "rust red", "white", "yellow")
SPICES = ("dill", "fennel", "pepper", "juniper", "thyme", "caraway", "sorrel")


def word(rng: random.Random, parts: int) -> str:
    """Return one invented word, built from syllables."""
    return "".join(rng.choice(ONSETS) + rng.choice(VOWELS) + rng.choice(CODAS) for _ in range(parts)).capitalize()


def person(rng: random.Random) -> str:
    return f"{word(rng, 2)} {word(rng, 2)}"


def place(rng: random.Random) -> str:
    return word(rng, 1) + rng.choice(PLACE_ENDS)


def sentence(rng: random.Random) -> str:
    """Return one invented sentence."""
    year = rng.randint(1620, 1890)
    text = rng.choice(TEMPLATES).format(
        person=person(rng), person2=person(rng), place=place(rng), place2=place(rng), job=rng.choice(JOBS),
        things=rng.choice(THINGS), building=rng.choice(BUILDINGS), feature=rng.choice(FEATURES),
        month=rng.choice(MONTHS), year=year, year2=year + rng.randint(3, 40), n=rng.randint(12, 480),
        small=rng.randint(2, 9), big=rng.randint(600, 9000), price=rng.randint(3, 95), weather=rng.choice(WEATHER),
        colour=rng.choice(COLOURS), spice=rng.choice(SPICES),
    )
    return text[0].upper() + text[1:]


def prose(seed: int, chars: int) -> str:
    """Return invented paragraphs of about this many characters. The same seed gives the same text."""
    rng = random.Random(seed)
    seen: set[str] = set()
    paragraphs, size = [], 0
    while size < chars:
        lines, count = [], rng.randint(4, 7)
        while len(lines) < count:
            line = sentence(rng)
            if line not in seen:
                seen.add(line)
                lines.append(line)
        paragraph = " ".join(lines)
        paragraphs.append(paragraph)
        size += len(paragraph) + 2
    return "\n\n".join(paragraphs)[:chars].rsplit(" ", 1)[0] + "."


def insert(text: str, sentence_text: str, share: float) -> str:
    """Put a sentence into the text at a paragraph break near the given share of its length (0 to 1)."""
    breaks = [i for i in range(len(text)) if text.startswith("\n\n", i)] or [len(text)]
    target = min(breaks, key=lambda i: abs(i - share * len(text)))
    return text[:target] + "\n\n" + sentence_text + text[target:]
