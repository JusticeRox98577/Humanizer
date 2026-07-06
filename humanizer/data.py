"""Curated linguistic data that drives the rule-based humanization engine.

Everything here targets a *measurable* AI-detection signal:

* ``AI_PHRASES`` / ``AI_WORDS`` remove the vocabulary that large language
  models over-produce (the "delve / tapestry / it is important to note"
  family). Detectors and humans alike treat these as tells.
* ``CONTRACTIONS`` reintroduce the informal contractions that formal LLM
  prose tends to avoid.
* ``SYNONYMS`` provide conservative, meaning-preserving swaps that raise the
  perplexity of the text (a common word replaced by a rarer-but-valid one is
  "more surprising" to the language model a detector runs under the hood).

The lists are intentionally conservative: a humanizer that mangles meaning is
useless, so every mapping below preserves the sense of the original.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Multi-word AI tells.  Keys are matched case-insensitively as whole phrases;
# values are the replacement (empty string = delete the phrase and tidy up).
# Order matters a little: longer phrases are applied before shorter ones by
# the engine, so list the long ones here and the engine sorts by length.
# ---------------------------------------------------------------------------
AI_PHRASES: dict[str, str] = {
    "it is important to note that": "",
    "it's important to note that": "",
    "it is worth noting that": "",
    "it should be noted that": "",
    "it is important to remember that": "",
    "it is crucial to understand that": "",
    "it is essential to recognize that": "",
    "in today's fast-paced world": "",
    "in today's digital age": "",
    "in the ever-evolving landscape of": "in",
    "in the realm of": "in",
    "when it comes to": "with",
    "at the end of the day": "ultimately",
    "navigating the complexities of": "handling",
    "navigate the complexities of": "handle",
    "a testament to": "proof of",
    "plays a crucial role in": "is key to",
    "plays a vital role in": "is key to",
    "plays a pivotal role in": "is key to",
    "plays a significant role in": "matters for",
    "it is worth mentioning that": "",
    "needless to say": "",
    "as previously mentioned": "as noted",
    "in conclusion": "so",
    "to sum up": "in short",
    "in summary": "in short",
    "first and foremost": "first",
    "last but not least": "finally",
    "a wide range of": "many",
    "a myriad of": "many",
    "a plethora of": "plenty of",
    "a variety of": "several",
    "in order to": "to",
    "due to the fact that": "because",
    "for the purpose of": "for",
    "with regard to": "about",
    "in terms of": "for",
    "the fact that": "that",
    "on the other hand": "but",
    "as a matter of fact": "in fact",
    "it goes without saying that": "",
    "this article will": "this will",
    "this essay will": "this will",
    "let us delve into": "let's look at",
    "let's delve into": "let's look at",
    "delve deeper into": "look closer at",
    "dive deeper into": "look closer at",
    "shed light on": "explain",
    "pave the way for": "enable",
    "paving the way for": "enabling",
    "in the grand scheme of things": "overall",
    "the world of": "",
    "when it comes down to it": "really",
    "more often than not": "usually",
    "an integral part of": "central to",
    "a double-edged sword": "a trade-off",
    "the bottom line is": "basically",
}

# ---------------------------------------------------------------------------
# Single-word AI tells -> plainer alternatives.  These are the words that
# spike in LLM output relative to human writing.
# ---------------------------------------------------------------------------
AI_WORDS: dict[str, str] = {
    "delve": "look",
    "delving": "looking",
    "tapestry": "mix",
    "leverage": "use",
    "leveraging": "using",
    "utilize": "use",
    "utilizes": "uses",
    "utilizing": "using",
    "utilization": "use",
    "facilitate": "help",
    "facilitates": "helps",
    "commence": "start",
    "commences": "starts",
    "endeavor": "try",
    "endeavour": "try",
    "myriad": "many",
    "plethora": "plenty",
    # NB: sentence-initial transitions (furthermore, moreover, additionally,
    # consequently, subsequently, nevertheless, nonetheless, however, therefore,
    # thus, hence) are handled by TRANSITION_STARTS instead, which varies the
    # replacement so we don't collapse them all to a repetitive "also".
    "notwithstanding": "despite that",
    "henceforth": "from now on",
    "thereby": "so",
    "wherein": "where",
    "whilst": "while",
    "amongst": "among",
    "utmost": "greatest",
    "paramount": "key",
    "pivotal": "key",
    "crucial": "key",
    "vital": "important",
    "robust": "strong",
    "seamless": "smooth",
    "seamlessly": "smoothly",
    "holistic": "complete",
    "multifaceted": "complex",
    "nuanced": "subtle",
    "intricate": "complex",
    "intricacies": "details",
    "comprehensive": "full",
    "underscore": "highlight",
    "underscores": "highlights",
    "showcasing": "showing",
    "showcase": "show",
    "elevate": "raise",
    "elevates": "raises",
    "foster": "build",
    "fostering": "building",
    "cultivate": "grow",
    "harness": "use",
    "harnessing": "using",
    "unveil": "reveal",
    "unveiling": "revealing",
    "realm": "area",
    "landscape": "field",
    "ecosystem": "system",
    "synergy": "teamwork",
    "paradigm": "model",
    "testament": "proof",
    "embark": "start",
    "embarking": "starting",
    "profound": "deep",
    "profoundly": "deeply",
    "invaluable": "valuable",
    "unparalleled": "unmatched",
    "unprecedented": "new",
    "transformative": "major",
    "groundbreaking": "new",
    "cutting-edge": "advanced",
    "state-of-the-art": "advanced",
    "game-changer": "big deal",
    "myriad of": "many",
    "aforementioned": "earlier",
    "optimal": "best",
    "optimize": "improve",
    "optimizing": "improving",
    "streamline": "simplify",
    "streamlined": "simplified",
    "spearhead": "lead",
    "bolster": "boost",
    "garner": "get",
    "garnered": "got",
    "myriads": "many",
    "encompass": "cover",
    "encompasses": "covers",
    "encompassing": "covering",
    "ubiquitous": "common",
    "quintessential": "classic",
    "meticulous": "careful",
    "meticulously": "carefully",
    "arduous": "hard",
    "vibrant": "lively",
    "bustling": "busy",
    "dynamic": "changing",
    "innovative": "new",
    "empower": "enable",
    "empowering": "enabling",
    "resonate": "connect",
    "resonates": "connects",
    "captivating": "engaging",
    "compelling": "strong",
}

# ---------------------------------------------------------------------------
# Contractions.  Applied only when the two words appear together, so we do not
# accidentally contract across clause boundaries.
# ---------------------------------------------------------------------------
CONTRACTIONS: dict[str, str] = {
    "it is": "it's",
    "it has": "it's",
    "that is": "that's",
    "there is": "there's",
    "here is": "here's",
    "he is": "he's",
    "she is": "she's",
    "what is": "what's",
    "who is": "who's",
    "let us": "let's",
    "do not": "don't",
    "does not": "doesn't",
    "did not": "didn't",
    "is not": "isn't",
    "are not": "aren't",
    "was not": "wasn't",
    "were not": "weren't",
    "has not": "hasn't",
    "have not": "haven't",
    "had not": "hadn't",
    "will not": "won't",
    "would not": "wouldn't",
    "should not": "shouldn't",
    "could not": "couldn't",
    "cannot": "can't",
    "can not": "can't",
    "must not": "mustn't",
    "you are": "you're",
    "we are": "we're",
    "they are": "they're",
    "you will": "you'll",
    "we will": "we'll",
    "they will": "they'll",
    "i will": "I'll",
    "i am": "I'm",
    "i have": "I've",
    "you have": "you've",
    "we have": "we've",
    "they have": "they've",
    "would have": "would've",
    "should have": "should've",
    "could have": "could've",
    "you would": "you'd",
    "they would": "they'd",
}

# ---------------------------------------------------------------------------
# Conservative synonym swaps used to raise perplexity.  Every value is a valid,
# roughly-equivalent replacement for the key.  The engine swaps only a fraction
# of eligible words so the text does not read like a thesaurus explosion.
# ---------------------------------------------------------------------------
SYNONYMS: dict[str, list[str]] = {
    "important": ["key", "big", "major"],
    "very": ["really", "quite", "pretty"],
    "good": ["solid", "decent", "strong"],
    "bad": ["poor", "rough", "weak"],
    "big": ["large", "huge", "massive"],
    "small": ["tiny", "little", "minor"],
    "many": ["plenty of", "lots of", "loads of"],
    "help": ["assist", "aid"],
    "show": ["reveal", "point to"],
    "make": ["build", "create"],
    "use": ["rely on", "work with"],
    "problem": ["issue", "snag", "hitch"],
    "difficult": ["tough", "tricky", "hard"],
    "easy": ["simple", "straightforward"],
    "quickly": ["fast", "in no time"],
    "however": ["but", "though", "still"],
    "therefore": ["so", "which means"],
    "because": ["since", "as"],
    "start": ["kick off", "begin"],
    "end": ["wrap up", "finish"],
    "increase": ["grow", "climb", "rise"],
    "decrease": ["drop", "fall", "shrink"],
    "understand": ["get", "grasp"],
    "think": ["figure", "reckon"],
    "look": ["check", "peek"],
    "get": ["grab", "pick up"],
    "a lot": ["tons", "loads"],
    "amazing": ["great", "awesome"],
    "interesting": ["neat", "cool"],
}

# ---------------------------------------------------------------------------
# Stiff sentence-initial transitions -> conversational replacements (or drop).
# The engine varies these to add burstiness at the start of sentences.
# ---------------------------------------------------------------------------
TRANSITION_STARTS: dict[str, list[str]] = {
    "furthermore": ["Plus,", "On top of that,", "And", "Also,"],
    "moreover": ["Plus,", "What's more,", "And", "Also,"],
    "additionally": ["Also,", "On top of that,", "Plus,"],
    "consequently": ["So", "As a result,", "Because of that,"],
    "subsequently": ["Then", "After that,", "Later,"],
    "however": ["But", "That said,", "Still,", "Then again,"],
    "nevertheless": ["Still,", "Even so,", "That said,"],
    "nonetheless": ["Still,", "Even so,"],
    "therefore": ["So", "Which means", "That's why"],
    "thus": ["So", "That's why"],
    "hence": ["So", "That's why"],
    "indeed": ["Really,", "In fact,"],
    "notably": ["Worth noting,", "In particular,"],
}

# Very short interjections we can occasionally splice in to add burstiness.
# Used sparingly by the burstiness pass.
SHORT_INTERJECTIONS: list[str] = [
    "Here's the thing.",
    "That matters.",
    "It adds up.",
    "Simple as that.",
    "No surprise there.",
    "That's the point.",
]

# The 200-ish most common English words, used by the scorer to estimate how
# "predictable" (low-perplexity) the vocabulary is.
COMMON_WORDS: frozenset[str] = frozenset(
    """the be to of and a in that have i it for not on with he as you do at this
    but his by from they we say her she or an will my one all would there their
    what so up out if about who get which go me when make can like time no just
    him know take people into year your good some could them see other than then
    now look only come its over think also back after use two how our work first
    well way even new want because any these give day most us is are was were been
    being had has more much many such very own same those here where why while
    should must may might shall each few both between under again further once
    against during before above below off down through over""".split()
)
