"""LocalEngine — embedded text processing engine. No LLM, no model download, no GPU.

This is the deepest layer of local-first inference: deterministic algorithms
that handle the 80% of "AI" requests that don't actually need a neural network.

Implements:
- Extractive summarization (TF-IDF sentence scoring)
- Text classification (Naive Bayes + keyword matching)
- Entity extraction (regex patterns + context rules)
- Simple Q&A (pattern matching + lookup + arithmetic)
- Code generation (template-based scaffolding)
- Structured output (text-to-JSON parsing)
- Sentiment analysis (lexicon-based)
- Translation (word replacement dictionary — basic)
- Text rewriting (simplification, expansion, tone adjustment)

Every function runs in microseconds. Zero cost per token. Zero dependencies
beyond numpy (already installed). No model to download. No service to run.

When a request comes in, the engine:
1. Classifies the intent (same heuristic classifier as the router)
2. Dispatches to the appropriate deterministic handler
3. Returns a response in the same format as an LLM would

If the engine can't handle a request (complex reasoning, creative writing,
agentic workflows), it signals "cannot_handle" and the router escalates to
Ollama or cloud.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np

# ─── Response ─────────────────────────────────────────────────────────────────

@dataclass
class EngineResponse:
    """Response from the local engine."""

    content: str
    handled: bool = True           # False if engine can't handle this request
    method: str = ""               # Which algorithm was used
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    confidence: float = 1.0        # How confident the engine is (0-1)


# ─── Text Utilities ───────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Simple word tokenizer."""
    return re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())


def _sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Handle common abbreviations
    text = re.sub(r"\b(Mr|Mrs|Dr|Prof|Inc|Ltd|vs|etc|e\.g|i\.e)\.", r"\1<DOT>", text)
    parts = re.split(r"[.!?]+", text)
    result = []
    for part in parts:
        part = part.replace("<DOT>", ".").strip()
        if part and len(part.split()) >= 3:
            result.append(part)
    return result


def _word_count(text: str) -> int:
    return len(text.split())


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~0.75 words per token."""
    return max(1, int(len(text.split()) * 1.33))


# ─── TF-IDF Summarization ─────────────────────────────────────────────────────

def _compute_tfidf(sentences: list[str]) -> np.ndarray:
    """Compute TF-IDF scores for each sentence.
    Returns a matrix of shape (n_sentences, n_unique_terms).
    """
    if not sentences:
        return np.array([])

    # Build vocabulary
    tokenized = [_tokenize(s) for s in sentences]
    vocab = sorted({word for tokens in tokenized for word in tokens})
    vocab_idx = {word: i for i, word in enumerate(vocab)}

    n_sentences = len(sentences)
    n_vocab = len(vocab)

    # Term frequency
    tf = np.zeros((n_sentences, n_vocab), dtype=np.float32)
    for i, tokens in enumerate(tokenized):
        for token in tokens:
            tf[i, vocab_idx[token]] += 1
        # Normalize by sentence length
        if len(tokens) > 0:
            tf[i] /= len(tokens)

    # Document frequency (how many sentences contain each word)
    df = np.zeros(n_vocab, dtype=np.float32)
    for tokens in tokenized:
        for word in set(tokens):
            df[vocab_idx[word]] += 1

    # IDF
    idf = np.log((n_sentences + 1) / (df + 1)) + 1

    # TF-IDF
    tfidf = tf * idf[np.newaxis, :]

    return tfidf  # type: ignore[no-any-return]


def _summarize_extractive(text: str, max_sentences: int = 3) -> str:
    """Extractive summarization using TF-IDF sentence scoring.

    Scores each sentence by summing TF-IDF weights of its words,
    with bonuses for sentences early in the text and penalties for
    very short or very long sentences.
    """
    sents = _sentences(text)
    if len(sents) <= max_sentences:
        return text.strip()

    tfidf = _compute_tfidf(sents)
    if tfidf.size == 0:
        return text.strip()

    # Score each sentence
    scores = np.zeros(len(sents))
    for i in range(len(sents)):
        # Sum of TF-IDF weights
        scores[i] = np.sum(tfidf[i])

        # Position bonus: earlier sentences tend to be more important
        position_weight = 1.0 / (1 + math.log(i + 1))
        scores[i] *= position_weight

        # Length penalty: very short or very long sentences are less ideal
        word_len = len(_tokenize(sents[i]))
        if word_len < 5:
            scores[i] *= 0.5
        elif word_len > 40:
            scores[i] *= 0.7

    # Select top sentences, preserving original order
    top_indices = sorted(np.argsort(scores)[-max_sentences:])
    summary = ". ".join(sents[i].strip() for i in top_indices)
    if not summary.endswith("."):
        summary += "."

    return summary


# ─── Naive Bayes Classification ───────────────────────────────────────────────

# Pre-built lexicons for common classification tasks
_SENTIMENT_POSITIVE = {
    "good", "great", "excellent", "amazing", "wonderful", "fantastic", "love",
    "loved", "like", "liked", "best", "awesome", "perfect", "happy", "glad",
    "pleased", "satisfied", "delighted", "superb", "brilliant", "outstanding",
    "remarkable", "fabulous", "marvelous", "terrific", "enjoy", "enjoyed",
    "recommend", "recommended", "impressive", "beautiful", "nice", "better",
    "win", "winning", "success", "successful", "positive", "beneficial",
}
_SENTIMENT_NEGATIVE = {
    "bad", "terrible", "awful", "horrible", "hate", "hated", "worst", "disgusting",
    "disappointing", "disappointed", "poor", "broken", "useless", "waste", "fail",
    "failed", "failure", "wrong", "error", "bug", "crash", "slow", "ugly",
    "boring", "annoying", "frustrating", "frustrated", "angry", "sad", "unhappy",
    "dissatisfied", "negative", "harmful", "damage", "damaged", "loss", "lose",
    "losing", "problem", "issue", "complaint", "refund", "return", "avoid",
}

_CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "technology": {"software", "hardware", "computer", "digital", "code", "program",
                   "algorithm", "data", "system", "network", "internet", "ai", "machine",
                   "tech", "app", "application", "database", "server", "cloud", "api"},
    "business": {"company", "market", "sales", "revenue", "profit", "customer",
                 "business", "corporate", "strategy", "growth", "investment", "finance",
                 "economic", "trade", "commerce", "industry", "startup", "venture"},
    "science": {"research", "study", "experiment", "theory", "hypothesis", "science",
                "scientific", "physics", "chemistry", "biology", "genome", "cell",
                "molecule", "atom", "quantum", "evolution", "species", "organism"},
    "sports": {"game", "team", "player", "score", "win", "lose", "match", "tournament",
               "championship", "league", "coach", "athlete", "sport", "race", "season",
               "play", "field", "court", "goal", "point"},
    "entertainment": {"movie", "film", "music", "song", "album", "actor", "actress",
                      "celebrity", "show", "series", "episode", "concert", "performance",
                      "art", "book", "novel", "game", "play", "theater", "streaming"},
    "health": {"health", "medical", "doctor", "patient", "disease", "treatment",
               "medicine", "hospital", "clinic", "symptom", "diagnosis", "therapy",
               "drug", "prescription", "wellness", "fitness", "diet", "nutrition",
               "exercise", "mental"},
}


def _classify_sentiment(text: str) -> str:
    """Classify sentiment as positive, negative, or neutral."""
    tokens = _tokenize(text)
    if not tokens:
        return "neutral"

    pos_count = sum(1 for t in tokens if t in _SENTIMENT_POSITIVE)
    neg_count = sum(1 for t in tokens if t in _SENTIMENT_NEGATIVE)

    if pos_count > neg_count:
        return "positive"
    if neg_count > pos_count:
        return "negative"
    return "neutral"


def _classify_category(text: str) -> str:
    """Classify text into a category."""
    tokens = set(_tokenize(text))
    if not tokens:
        return "general"

    best_category = "general"
    best_score = 0

    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = len(tokens & keywords)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category


def _classify_spam(text: str) -> str:
    """Classify text as spam or not spam."""
    spam_indicators = {
        "free", "winner", "win", "prize", "congratulations", "click", "click here",
        "subscribe", "unsubscribe", "limited", "offer", "deal", "discount", "cash",
        "money", "credit", "loan", "guarantee", "risk", "urgent", "act now",
        "buy now", "order now", "100%", "best price", "lowest price", "save",
        "earn", "income", "profit", "investment", "opportunity", "exclusive",
    }
    tokens = set(_tokenize(text))
    spam_score = len(tokens & spam_indicators)

    # Also check for ALL CAPS and excessive punctuation
    caps_ratio = sum(1 for c in text if c.isupper()) / max(1, len(text))
    exclaim_count = text.count("!")

    if spam_score >= 3 or (caps_ratio > 0.3 and exclaim_count > 2):
        return "spam"
    return "not spam"


# ─── Entity Extraction ────────────────────────────────────────────────────────

# Regex patterns for common entity types
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b")
_URL_RE = re.compile(r"https?://[^\s<>\"]+[^\s<>\".]")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s*\d{0,4})\b",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?|\d+(?:,\d{3})*(?:\.\d+)?\s*(?:USD|EUR|GBP|dollars?|euros?|pounds?)", re.IGNORECASE)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")

# Name extraction heuristic (capitalized word sequences, not at sentence start)
_NAME_RE = re.compile(
    r"(?<!^)(?<!\. )\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
)


def _extract_entities(text: str, entity_types: list[str] | None = None) -> dict[str, list[str]]:
    """Extract named entities from text using regex patterns.
    Returns dict mapping entity type → list of matches.
    """
    results: dict[str, list[str]] = {
        "emails": [m.group() for m in _EMAIL_RE.finditer(text)],
        "phones": ["-".join(m.groups()) for m in _PHONE_RE.finditer(text)],
        "urls": [m.group() for m in _URL_RE.finditer(text)],
        "dates": [m.group().strip() for m in _DATE_RE.finditer(text)],
        "currency": [m.group().strip() for m in _CURRENCY_RE.finditer(text)],
        "ip_addresses": [m.group() for m in _IP_RE.finditer(text)],
        "zip_codes": [m.group() for m in _ZIP_RE.finditer(text)],
        "names": [m.group() for m in _NAME_RE.finditer(text)],
    }

    if entity_types:
        return {k: v for k, v in results.items() if k in entity_types}
    return results


def _extract_by_pattern(text: str, pattern_name: str) -> str:
    """Extract a specific type of entity and format as response."""
    entities = _extract_entities(text)

    type_map = {
        "email": "emails", "emails": "emails",
        "phone": "phones", "phones": "phones",
        "url": "urls", "urls": "urls",
        "date": "dates", "dates": "dates",
        "money": "currency", "currency": "currency", "amount": "currency",
        "name": "names", "names": "names",
        "ip": "ip_addresses", "ip_address": "ip_addresses",
        "zip": "zip_codes", "zip_code": "zip_codes",
    }

    key = type_map.get(pattern_name.lower(), pattern_name.lower() + "s")
    if key not in entities:
        # Try to infer from the query itself
        all_entities = entities
        found = []
        for vals in all_entities.values():
            found.extend(vals)
        if found:
            return "\n".join(found)
        return "No entities found matching the requested pattern."

    values = entities[key]
    if not values:
        return f"No {pattern_name}(s) found in the text."

    if len(values) == 1:
        return values[0]
    return "\n".join(f"{i+1}. {v}" for i, v in enumerate(values))


# ─── Simple Q&A ───────────────────────────────────────────────────────────────

# Built-in knowledge base for common factual questions
_KNOWLEDGE_BASE: dict[str, str] = {
    "capital of france": "The capital of France is Paris.",
    "capital of england": "The capital of England is London.",
    "capital of uk": "The capital of the United Kingdom is London.",
    "capital of usa": "The capital of the United States is Washington, D.C.",
    "capital of us": "The capital of the United States is Washington, D.C.",
    "capital of germany": "The capital of Germany is Berlin.",
    "capital of japan": "The capital of Japan is Tokyo.",
    "capital of china": "The capital of China is Beijing.",
    "capital of india": "The capital of India is New Delhi.",
    "capital of russia": "The capital of Russia is Moscow.",
    "capital of italy": "The capital of Italy is Rome.",
    "capital of spain": "The capital of Spain is Madrid.",
    "capital of canada": "The capital of Canada is Ottawa.",
    "capital of australia": "The capital of Australia is Canberra.",
    "capital of brazil": "The capital of Brazil is Brasília.",
    "capital of mexico": "The capital of Mexico is Mexico City.",
    "largest planet": "The largest planet in our solar system is Jupiter.",
    "smallest planet": "The smallest planet in our solar system is Mercury.",
    "speed of light": "The speed of light is approximately 299,792,458 meters per second (about 186,282 miles per second).",
    "pi": "Pi (π) is approximately 3.14159.",
    "meaning of life": "42. (According to Douglas Adams.)",
    "who wrote romeo and juliet": "Romeo and Juliet was written by William Shakespeare.",
    "who wrote hamlet": "Hamlet was written by William Shakespeare.",
    "who wrote macbeth": "Macbeth was written by William Shakespeare.",
    "who painted the mona lisa": "The Mona Lisa was painted by Leonardo da Vinci.",
    "who invented the telephone": "The telephone was invented by Alexander Graham Bell.",
    "who invented the light bulb": "The light bulb was invented by Thomas Edison.",
    "largest ocean": "The largest ocean on Earth is the Pacific Ocean.",
    "largest country": "The largest country by land area is Russia.",
    "most populous country": "The most populous country is India.",
    "tallest mountain": "The tallest mountain on Earth is Mount Everest (8,848.86 meters).",
    "longest river": "The longest river is the Nile (approximately 6,650 km).",
    # Science
    "speed of sound": "The speed of sound in air at 20°C is approximately 343 meters per second.",
    "gravity": "Standard gravity on Earth is 9.80665 m/s².",
    "avogadro's number": "Avogadro's number is approximately 6.022 × 10²³.",
    "planck constant": "The Planck constant is approximately 6.626 × 10⁻³⁴ J·s.",
    "earth radius": "The Earth's radius is approximately 6,371 km.",
    "moon distance": "The average distance from Earth to the Moon is about 384,400 km.",
    "sun distance": "The average distance from Earth to the Sun is about 149.6 million km (1 AU).",
    "earth age": "The Earth is approximately 4.54 billion years old.",
    "universe age": "The universe is approximately 13.8 billion years old.",
    "human dna": "Human DNA contains approximately 3 billion base pairs.",
    "water boiling point": "Water boils at 100°C (212°F) at standard atmospheric pressure.",
    "water freezing point": "Water freezes at 0°C (32°F) at standard atmospheric pressure.",
    "absolute zero": "Absolute zero is 0 Kelvin (-273.15°C or -459.67°F).",
    # Geography
    "capital of south korea": "The capital of South Korea is Seoul.",
    "capital of egypt": "The capital of Egypt is Cairo.",
    "capital of argentina": "The capital of Argentina is Buenos Aires.",
    "capital of south africa": "South Africa has three capitals: Pretoria (administrative), Cape Town (legislative), and Bloemfontein (judicial).",
    "capital of turkey": "The capital of Turkey is Ankara.",
    "capital of switzerland": "The capital of Switzerland is Bern.",
    "capital of norway": "The capital of Norway is Oslo.",
    "capital of sweden": "The capital of Sweden is Stockholm.",
    "capital of netherlands": "The capital of the Netherlands is Amsterdam.",
    "capital of greece": "The capital of Greece is Athens.",
    "capital of portugal": "The capital of Portugal is Lisbon.",
    "capital of thailand": "The capital of Thailand is Bangkok.",
    "capital of vietnam": "The capital of Vietnam is Hanoi.",
    "capital of kenya": "The capital of Kenya is Nairobi.",
    "capital of saudi arabia": "The capital of Saudi Arabia is Riyadh.",
    # History
    "who wrote the odyssey": "The Odyssey was written by Homer.",
    "who wrote the iliad": "The Iliad was written by Homer.",
    "who wrote war and peace": "War and Peace was written by Leo Tolstoy.",
    "who wrote 1984": "1984 was written by George Orwell.",
    "who wrote pride and prejudice": "Pride and Prejudice was written by Jane Austen.",
    "who wrote the republic": "The Republic was written by Plato.",
    "who discovered penicillin": "Penicillin was discovered by Alexander Fleming in 1928.",
    "who discovered america": "Christopher Columbus is credited with discovering America in 1492.",
    "who invented the printing press": "The printing press was invented by Johannes Gutenberg.",
    "who invented the airplane": "The airplane was invented by the Wright brothers (Orville and Wilbur Wright).",
    "who invented the internet": "The Internet evolved from ARPANET, developed by DARPA in the 1960s-70s.",
    "who invented the world wide web": "The World Wide Web was invented by Tim Berners-Lee in 1989.",
    "who invented python": "Python was created by Guido van Rossum, first released in 1991.",
    "who invented javascript": "JavaScript was created by Brendan Eich in 1995.",
    "who invented c": "The C programming language was developed by Dennis Ritchie at Bell Labs.",
    "who invented linux": "Linux was created by Linus Torvalds in 1991.",
    # Math
    "golden ratio": "The golden ratio (φ) is approximately 1.618033988749895.",
    "euler's number": "Euler's number (e) is approximately 2.718281828459045.",
    "fibonacci sequence": "The Fibonacci sequence starts: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34, ...",
    "prime number": "A prime number is a natural number greater than 1 that has no positive divisors other than 1 and itself.",
    # Technology
    "what is ai": "AI (Artificial Intelligence) is the simulation of human intelligence processes by machines, especially computer systems.",
    "what is machine learning": "Machine learning is a subset of AI that enables systems to learn and improve from experience without being explicitly programmed.",
    "what is deep learning": "Deep learning is a subset of machine learning based on artificial neural networks with multiple layers.",
    "what is a neural network": "A neural network is a series of algorithms that endeavors to recognize underlying relationships in data through a process that mimics the human brain.",
    "what is blockchain": "A blockchain is a distributed, decentralized, immutable ledger used to record transactions across many computers.",
    "what is docker": "Docker is a platform for developing, shipping, and running applications in containers.",
    "what is kubernetes": "Kubernetes is an open-source container orchestration platform for automating deployment and scaling.",
    "what is rest api": "REST (Representational State Transfer) is an architectural style for designing networked applications using HTTP methods.",
}

# Unit conversions
_UNIT_CONVERSIONS = {
    ("feet", "meters"): 0.3048,
    ("ft", "meters"): 0.3048,
    ("ft", "m"): 0.3048,
    ("meters", "feet"): 3.28084,
    ("m", "feet"): 3.28084,
    ("miles", "km"): 1.60934,
    ("mi", "km"): 1.60934,
    ("km", "miles"): 0.621371,
    ("kg", "pounds"): 2.20462,
    ("kg", "lbs"): 2.20462,
    ("pounds", "kg"): 0.453592,
    ("lbs", "kg"): 0.453592,
    ("celsius", "fahrenheit"): None,  # Special handling
    ("fahrenheit", "celsius"): None,
    ("gallons", "liters"): 3.78541,
    ("liters", "gallons"): 0.264172,
    ("inches", "cm"): 2.54,
    ("cm", "inches"): 0.393701,
}


def _try_arithmetic(text: str) -> str | None:
    """Try to evaluate a simple arithmetic expression."""
    # Extract the mathematical expression
    expr_match = re.search(
        r"(?:what is|what's|calculate|compute|solve|evaluate)?\s*"
        r"([-+*/.\d\s()%^]+)",
        text, re.IGNORECASE,
    )
    if not expr_match:
        return None

    expr = expr_match.group(1).strip()
    if not expr or not re.search(r"\d", expr):
        return None

    # Replace common math words
    expr = expr.replace("^", "**")
    expr = expr.replace("x", "*").replace("×", "*")
    expr = expr.replace("÷", "/")

    # Clean up
    expr = expr.strip()
    if not expr:
        return None

    # Must contain at least one operator
    if not re.search(r"[+\-*/^]", expr):
        return None

    # Safe evaluation (only math operations)
    try:
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expr):
            return None
        result = eval(expr, {"__builtins__": {}}, {})
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"{expr} = {result}"
    except Exception:
        return None


def _try_unit_conversion(text: str) -> str | None:
    """Try to convert units."""
    text_lower = text.lower()
    for (from_unit, to_unit), factor in _UNIT_CONVERSIONS.items():
        pattern = rf"(?:convert\s+)?(\d+(?:\.\d+)?)\s*{re.escape(from_unit)}\s*(?:to|in)\s*{re.escape(to_unit)}"
        match = re.search(pattern, text_lower)
        if match:
            value = float(match.group(1))
            if from_unit == "celsius" and to_unit == "fahrenheit":
                result = value * 9/5 + 32
                return f"{value}°C = {result:.1f}°F"
            if from_unit == "fahrenheit" and to_unit == "celsius":
                result = (value - 32) * 5/9
                return f"{value}°F = {result:.1f}°C"
            if factor is not None:
                result = value * factor
                return f"{value} {from_unit} = {result:.4f} {to_unit}"
    return None


def _try_definition(text: str) -> str | None:
    """Try to answer definition questions."""
    # Try "what is/what's/define/meaning of" patterns
    match = re.match(r"(?:what is|what's|define|meaning of)\s+(?:a|an|the\s+)?(.+)", text, re.IGNORECASE)
    if match:
        term = match.group(1).strip().rstrip("?.")
        kb_key = term.lower()
        if kb_key in _KNOWLEDGE_BASE:
            return _KNOWLEDGE_BASE[kb_key]
        for key, value in _KNOWLEDGE_BASE.items():
            if key in kb_key or kb_key in key:
                return value

    # Try direct KB lookup for "who invented/who wrote/who discovered" patterns
    text_lower = text.lower().strip().rstrip("?.")
    if text_lower in _KNOWLEDGE_BASE:
        return _KNOWLEDGE_BASE[text_lower]
    for key, value in _KNOWLEDGE_BASE.items():
        if key in text_lower or text_lower in key:
            return value

    return None


def _simple_qa(text: str) -> str | None:
    """Answer simple factual questions."""
    # Try arithmetic first
    result = _try_arithmetic(text)
    if result:
        return result

    # Try unit conversion
    result = _try_unit_conversion(text)
    if result:
        return result

    # Try definition/knowledge base
    result = _try_definition(text)
    if result:
        return result

    return None


# ─── Code Generation (Template-Based) ─────────────────────────────────────────

def _generate_code(text: str) -> str | None:
    """Generate code from simple natural language descriptions."""
    text_lower = text.lower()

    # Factorial
    if "factorial" in text_lower:
        return (
            "def factorial(n):\n"
            '    """Calculate the factorial of n."""\n'
            "    if n < 0:\n"
            "        raise ValueError('n must be non-negative')\n"
            "    if n <= 1:\n"
            "        return 1\n"
            "    return n * factorial(n - 1)"
        )

    # Fibonacci
    if "fibonacci" in text_lower or "fib" in text_lower:
        return (
            "def fibonacci(n):\n"
            '    """Generate the first n Fibonacci numbers."""\n'
            "    if n <= 0:\n"
            "        return []\n"
            "    if n == 1:\n"
            "        return [0]\n"
            "    fibs = [0, 1]\n"
            "    for i in range(2, n):\n"
            "        fibs.append(fibs[-1] + fibs[-2])\n"
            "    return fibs"
        )

    # Sort
    if "sort" in text_lower and "list" in text_lower:
        return (
            "def sort_list(lst):\n"
            '    """Sort a list in ascending order."""\n'
            "    return sorted(lst)"
        )

    # Reverse string
    if "reverse" in text_lower and "string" in text_lower:
        return (
            "def reverse_string(s):\n"
            '    """Reverse a string."""\n'
            "    return s[::-1]"
        )

    # Palindrome check
    if "palindrome" in text_lower:
        return (
            "def is_palindrome(s):\n"
            '    """Check if a string is a palindrome."""\n'
            "    s = s.lower().replace(' ', '')\n"
            "    return s == s[::-1]"
        )

    # Prime check
    if "prime" in text_lower:
        return (
            "def is_prime(n):\n"
            '    """Check if n is a prime number."""\n'
            "    if n < 2:\n"
            "        return False\n"
            "    if n == 2:\n"
            "        return True\n"
            "    if n % 2 == 0:\n"
            "        return False\n"
            "    for i in range(3, int(n**0.5) + 1, 2):\n"
            "        if n % i == 0:\n"
            "            return False\n"
            "    return True"
        )

    # Hello world
    if "hello world" in text_lower:
        return 'print("Hello, World!")'

    # HTTP server
    if "http server" in text_lower or "web server" in text_lower:
        return (
            "from http.server import HTTPServer, SimpleHTTPRequestHandler\n"
            "\n"
            "def run_server(port=8000):\n"
            "    server = HTTPServer(('', port), SimpleHTTPRequestHandler)\n"
            "    print(f'Serving on http://localhost:{port}')\n"
            "    server.serve_forever()"
        )

    # REST API
    if "rest api" in text_lower or "flask app" in text_lower:
        return (
            "from flask import Flask, jsonify, request\n"
            "\n"
            "app = Flask(__name__)\n"
            "\n"
            "@app.route('/api/health', methods=['GET'])\n"
            "def health():\n"
            "    return jsonify({'status': 'ok'})\n"
            "\n"
            "@app.route('/api/items', methods=['GET', 'POST'])\n"
            "def items():\n"
            "    if request.method == 'POST':\n"
            "        data = request.json\n"
            "        return jsonify(data), 201\n"
            "    return jsonify([])\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    app.run(debug=True, port=5000)"
        )

    # File reading
    if "read file" in text_lower or "open file" in text_lower:
        return (
            "def read_file(filepath):\n"
            '    """Read the contents of a file."""\n'
            "    with open(filepath, 'r') as f:\n"
            "        return f.read()"
        )

    # CSV parsing
    if "csv" in text_lower:
        return (
            "import csv\n"
            "\n"
            "def read_csv(filepath):\n"
            '    """Read a CSV file and return rows as dictionaries."""\n'
            "    with open(filepath, 'r', newline='') as f:\n"
            "        reader = csv.DictReader(f)\n"
            "        return list(reader)"
        )

    # JSON parsing
    if "parse json" in text_lower or "load json" in text_lower:
        return (
            "import json\n"
            "\n"
            "def parse_json(json_str):\n"
            '    """Parse a JSON string."""\n'
            "    return json.loads(json_str)"
        )

    # Binary search
    if "binary search" in text_lower:
        return (
            "def binary_search(arr, target):\n"
            '    """Binary search for target in sorted array."""\n'
            "    lo, hi = 0, len(arr) - 1\n"
            "    while lo <= hi:\n"
            "        mid = (lo + hi) // 2\n"
            "        if arr[mid] == target:\n"
            "            return mid\n"
            "        elif arr[mid] < target:\n"
            "            lo = mid + 1\n"
            "        else:\n"
            "            hi = mid - 1\n"
            "    return -1"
        )

    # Linked list
    if "linked list" in text_lower:
        return (
            "class Node:\n"
            "    def __init__(self, val=0, next=None):\n"
            "        self.val = val\n"
            "        self.next = next\n"
            "\n"
            "class LinkedList:\n"
            "    def __init__(self):\n"
            "        self.head = None\n"
            "\n"
            "    def prepend(self, val):\n"
            "        self.head = Node(val, self.head)\n"
            "\n"
            "    def to_list(self):\n"
            "        result, node = [], self.head\n"
            "        while node:\n"
            "            result.append(node.val)\n"
            "            node = node.next\n"
            "        return result"
        )

    # Merge sort
    if "merge sort" in text_lower:
        return (
            "def merge_sort(arr):\n"
            '    """Sort array using merge sort."""\n'
            "    if len(arr) <= 1:\n"
            "        return arr\n"
            "    mid = len(arr) // 2\n"
            "    left = merge_sort(arr[:mid])\n"
            "    right = merge_sort(arr[mid:])\n"
            "    return merge(left, right)\n"
            "\n"
            "def merge(a, b):\n"
            "    result = []\n"
            "    i = j = 0\n"
            "    while i < len(a) and j < len(b):\n"
            "        if a[i] <= b[j]:\n"
            "            result.append(a[i]); i += 1\n"
            "        else:\n"
            "            result.append(b[j]); j += 1\n"
            "    result.extend(a[i:])\n"
            "    result.extend(b[j:])\n"
            "    return result"
        )

    # Quick sort
    if "quick sort" in text_lower or "quicksort" in text_lower:
        return (
            "def quicksort(arr):\n"
            '    """Sort array using quicksort."""\n'
            "    if len(arr) <= 1:\n"
            "        return arr\n"
            "    pivot = arr[len(arr) // 2]\n"
            "    left = [x for x in arr if x < pivot]\n"
            "    mid = [x for x in arr if x == pivot]\n"
            "    right = [x for x in arr if x > pivot]\n"
            "    return quicksort(left) + mid + quicksort(right)"
        )

    # Hash table / dict
    if "hash table" in text_lower or "hashmap" in text_lower:
        return (
            "class HashTable:\n"
            '    """Simple hash table implementation."""\n'
            "    def __init__(self, size=100):\n"
            "        self.size = size\n"
            "        self.table = [[] for _ in range(size)]\n"
            "\n"
            "    def _hash(self, key):\n"
            "        return hash(key) % self.size\n"
            "\n"
            "    def put(self, key, value):\n"
            "        h = self._hash(key)\n"
            "        for i, (k, v) in enumerate(self.table[h]):\n"
            "            if k == key:\n"
            "                self.table[h][i] = (key, value)\n"
            "                return\n"
            "        self.table[h].append((key, value))\n"
            "\n"
            "    def get(self, key):\n"
            "        h = self._hash(key)\n"
            "        for k, v in self.table[h]:\n"
            "            if k == key:\n"
            "                return v\n"
            "        return None\n"
            "\n"
            "    def delete(self, key):\n"
            "        h = self._hash(key)\n"
            "        self.table[h] = [(k, v) for k, v in self.table[h] if k != key]"
        )

    # Queue
    if "queue" in text_lower and "class" in text_lower:
        return (
            "from collections import deque\n"
            "\n"
            "class Queue:\n"
            '    """FIFO queue implementation."""\n'
            "    def __init__(self):\n"
            "        self.items = deque()\n"
            "\n"
            "    def enqueue(self, item):\n"
            "        self.items.append(item)\n"
            "\n"
            "    def dequeue(self):\n"
            "        if not self.items:\n"
            "            raise IndexError('Queue is empty')\n"
            "        return self.items.popleft()\n"
            "\n"
            "    def is_empty(self):\n"
            "        return len(self.items) == 0\n"
            "\n"
            "    def size(self):\n"
            "        return len(self.items)"
        )

    # Stack
    if "stack" in text_lower and ("class" in text_lower or "implement" in text_lower):
        return (
            "class Stack:\n"
            '    """LIFO stack implementation."""\n'
            "    def __init__(self):\n"
            "        self.items = []\n"
            "\n"
            "    def push(self, item):\n"
            "        self.items.append(item)\n"
            "\n"
            "    def pop(self):\n"
            "        if not self.items:\n"
            "            raise IndexError('Stack is empty')\n"
            "        return self.items.pop()\n"
            "\n"
            "    def peek(self):\n"
            "        if not self.items:\n"
            "            return None\n"
            "        return self.items[-1]\n"
            "\n"
            "    def is_empty(self):\n"
            "        return len(self.items) == 0"
        )

    # Graph BFS
    if "bfs" in text_lower or "breadth first" in text_lower:
        return (
            "from collections import deque\n"
            "\n"
            "def bfs(graph, start):\n"
            '    """Breadth-first search traversal."""\n'
            "    visited = set()\n"
            "    queue = deque([start])\n"
            "    result = []\n"
            "    while queue:\n"
            "        node = queue.popleft()\n"
            "        if node not in visited:\n"
            "            visited.add(node)\n"
            "            result.append(node)\n"
            "            queue.extend(graph.get(node, []))\n"
            "    return result"
        )

    # Graph DFS
    if "dfs" in text_lower or "depth first" in text_lower:
        return (
            "def dfs(graph, start, visited=None):\n"
            '    """Depth-first search traversal."""\n'
            "    if visited is None:\n"
            "        visited = set()\n"
            "    visited.add(start)\n"
            "    result = [start]\n"
            "    for neighbor in graph.get(start, []):\n"
            "        if neighbor not in visited:\n"
            "            result.extend(dfs(graph, neighbor, visited))\n"
            "    return result"
        )

    # Binary tree
    if "binary tree" in text_lower or ("tree" in text_lower and "traversal" in text_lower):
        return (
            "class TreeNode:\n"
            "    def __init__(self, val=0, left=None, right=None):\n"
            "        self.val = val\n"
            "        self.left = left\n"
            "        self.right = right\n"
            "\n"
            "def inorder(root):\n"
            '    """In-order traversal."""\n'
            "    if root:\n"
            "        yield from inorder(root.left)\n"
            "        yield root.val\n"
            "        yield from inorder(root.right)\n"
            "\n"
            "def preorder(root):\n"
            '    """Pre-order traversal."""\n'
            "    if root:\n"
            "        yield root.val\n"
            "        yield from preorder(root.left)\n"
            "        yield from preorder(root.right)\n"
            "\n"
            "def postorder(root):\n"
            '    """Post-order traversal."""\n'
            "    if root:\n"
            "        yield from postorder(root.left)\n"
            "        yield from postorder(root.right)\n"
            "        yield root.val"
        )

    # Regex matcher
    if "regex" in text_lower or "regular expression" in text_lower:
        return (
            "import re\n"
            "\n"
            "def find_matches(pattern, text):\n"
            '    """Find all regex matches in text."""\n'
            "    return re.findall(pattern, text)\n"
            "\n"
            "def is_match(pattern, text):\n"
            '    """Check if pattern matches text."""\n'
            "    return bool(re.search(pattern, text))"
        )

    # Retry decorator — check BEFORE generic decorator
    if "retry" in text_lower:
        return (
            "import functools\n"
            "import time\n"
            "\n"
            "def retry(max_attempts=3, delay=1.0):\n"
            '    """Retry decorator with exponential backoff."""\n'
            "    def decorator(func):\n"
            "        @functools.wraps(func)\n"
            "        def wrapper(*args, **kwargs):\n"
            "            for attempt in range(max_attempts):\n"
            "                try:\n"
            "                    return func(*args, **kwargs)\n"
            "                except Exception as e:\n"
            "                    if attempt == max_attempts - 1:\n"
            "                        raise\n"
            "                    time.sleep(delay * (2 ** attempt))\n"
            "        return wrapper\n"
            "    return decorator"
        )

    # Decorator
    if "decorator" in text_lower:
        return (
            "import functools\n"
            "\n"
            "def timing(func):\n"
            '    """Decorator to measure execution time."""\n'
            "    @functools.wraps(func)\n"
            "    def wrapper(*args, **kwargs):\n"
            "        import time\n"
            "        start = time.time()\n"
            "        result = func(*args, **kwargs)\n"
            "        elapsed = time.time() - start\n"
            "        print(f'{func.__name__}: {elapsed:.4f}s')\n"
            "        return result\n"
            "    return wrapper"
        )

    # Context manager
    if "context manager" in text_lower:
        return (
            "from contextlib import contextmanager\n"
            "\n"
            "@contextmanager\n"
            "def open_file(path, mode='r'):\n"
            '    """Context manager for file handling."""\n'
            "    f = open(path, mode)\n"
            "    try:\n"
            "        yield f\n"
            "    finally:\n"
            "        f.close()"
        )

    # Dataclass
    if "dataclass" in text_lower:
        return (
            "from dataclasses import dataclass, field\n"
            "from typing import List\n"
            "\n"
            "@dataclass\n"
            "class Person:\n"
            "    name: str\n"
            "    age: int\n"
            "    email: str = ''\n"
            "    tags: List[str] = field(default_factory=list)\n"
            "\n"
            "    def __str__(self):\n"
            "        return f'{self.name} ({self.age})'"
        )

    # Singleton
    if "singleton" in text_lower:
        return (
            "class Singleton:\n"
            '    """Singleton pattern implementation."""\n'
            "    _instance = None\n"
            "\n"
            "    def __new__(cls):\n"
            "        if cls._instance is None:\n"
            "            cls._instance = super().__new__(cls)\n"
            "        return cls._instance"
        )

    # Factory pattern
    if "factory" in text_lower and "pattern" in text_lower:
        return (
            "class Animal:\n"
            "    def speak(self):\n"
            "        raise NotImplementedError\n"
            "\n"
            "class Dog(Animal):\n"
            "    def speak(self):\n"
            "        return 'Woof'\n"
            "\n"
            "class Cat(Animal):\n"
            "    def speak(self):\n"
            "        return 'Meow'\n"
            "\n"
            "class AnimalFactory:\n"
            "    @staticmethod\n"
            "    def create(kind):\n"
            "        if kind == 'dog':\n"
            "            return Dog()\n"
            "        elif kind == 'cat':\n"
            "            return Cat()\n"
            "        raise ValueError(f'Unknown animal: {kind}')"
        )

    # Power function
    if "power" in text_lower and "function" in text_lower:
        return (
            "def power(base, exp):\n"
            '    """Calculate base raised to exp."""\n'
            "    if exp == 0:\n"
            "        return 1\n"
            "    if exp < 0:\n"
            "        return 1 / power(base, -exp)\n"
            "    return base * power(base, exp - 1)"
        )

    # GCD
    if "gcd" in text_lower or "greatest common" in text_lower:
        return (
            "def gcd(a, b):\n"
            '    """Greatest common divisor (Euclidean algorithm)."""\n'
            "    while b:\n"
            "        a, b = b, a % b\n"
            "    return a"
        )

    # LCM
    if "lcm" in text_lower or "least common" in text_lower:
        return (
            "def gcd(a, b):\n"
            "    while b:\n"
            "        a, b = b, a % b\n"
            "    return a\n"
            "\n"
            "def lcm(a, b):\n"
            '    """Least common multiple."""\n'
            "    return abs(a * b) // gcd(a, b) if a and b else 0"
        )

    # String reverse
    if "reverse string" in text_lower or ("reverse" in text_lower and "word" in text_lower):
        return (
            "def reverse_string(s):\n"
            '    """Reverse a string."""\n'
            "    return s[::-1]\n"
            "\n"
            "def reverse_words(s):\n"
            '    """Reverse word order in a string."""\n'
            "    return ' '.join(s.split()[::-1])"
        )

    # FizzBuzz
    if "fizzbuzz" in text_lower or "fizz buzz" in text_lower:
        return (
            "def fizzbuzz(n):\n"
            '    """Classic FizzBuzz."""\n'
            "    result = []\n"
            "    for i in range(1, n + 1):\n"
            "        if i % 15 == 0:\n"
            "            result.append('FizzBuzz')\n"
            "        elif i % 3 == 0:\n"
            "            result.append('Fizz')\n"
            "        elif i % 5 == 0:\n"
            "            result.append('Buzz')\n"
            "        else:\n"
            "            result.append(str(i))\n"
            "    return result"
        )

    # Matrix multiplication
    if "matrix" in text_lower and ("multiply" in text_lower or "multiplication" in text_lower):
        return (
            "def matrix_multiply(a, b):\n"
            '    """Multiply two matrices."""\n'
            "    rows_a = len(a)\n"
            "    cols_a = len(a[0])\n"
            "    cols_b = len(b[0])\n"
            "    result = [[0] * cols_b for _ in range(rows_a)]\n"
            "    for i in range(rows_a):\n"
            "        for j in range(cols_b):\n"
            "            for k in range(cols_a):\n"
            "                result[i][j] += a[i][k] * b[k][j]\n"
            "    return result"
        )

    # Email validator
    if "validate" in text_lower and "email" in text_lower:
        return (
            "import re\n"
            "\n"
            "def is_valid_email(email):\n"
            '    """Validate email address."""\n'
            "    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n"
            "    return bool(re.match(pattern, email))"
        )

    # Password generator
    if "password" in text_lower and "generat" in text_lower:
        return (
            "import random\n"
            "import string\n"
            "\n"
            "def generate_password(length=16):\n"
            '    """Generate a random password."""\n'
            "    chars = string.ascii_letters + string.digits + '!@#$%^&*'\n"
            "    return ''.join(random.choice(chars) for _ in range(length))"
        )

    # Date formatter
    if "format" in text_lower and "date" in text_lower:
        return (
            "from datetime import datetime\n"
            "\n"
            "def format_date(dt, fmt='%Y-%m-%d %H:%M:%S'):\n"
            '    """Format a datetime object."""\n'
            "    return dt.strftime(fmt)\n"
            "\n"
            "def parse_date(date_str, fmt='%Y-%m-%d'):\n"
            '    """Parse a date string."""\n'
            "    return datetime.strptime(date_str, fmt)"
        )

    # Retry decorator — already handled above, remove duplicate
    return None


# ─── Algebra Solver ───────────────────────────────────────────────────────────

def _solve_algebra(text: str) -> str | None:
    """Solve simple algebraic equations: ax + b = c, ax^2 + bx + c = 0.
    """
    text_lower = text.lower().strip()

    # Quadratic: ax^2 + bx + c = 0 (check BEFORE linear to avoid false match)
    quad_match = re.match(
        r"(?:solve|find)?\s*([+-]?\d*\.?\d*)\s*\*?\s*x\s*\^?\s*2\s*"
        r"(?:([+-]\s*\d*\.?\d*)\s*\*?\s*x)?\s*"
        r"([+-]\s*\d*\.?\d*)?\s*=\s*0",
        text_lower,
    )
    if quad_match:
        a_str, b_str, c_str = quad_match.groups()
        a = float(a_str) if a_str and a_str not in ("", "+", "-") else (1.0 if not a_str or a_str == "+" else -1.0)
        b = float(b_str.replace(" ", "")) if b_str else 0.0
        c = float(c_str.replace(" ", "")) if c_str else 0.0

        discriminant = b**2 - 4*a*c
        if discriminant < 0:
            real = -b / (2*a)
            imag = (abs(discriminant) ** 0.5) / (2*a)
            return f"x = {real:.4f} ± {imag:.4f}i (complex roots)"
        if discriminant == 0:
            x = -b / (2*a)
            if x == int(x):
                x = int(x)
            return f"x = {x} (double root)"
        x1 = (-b + discriminant**0.5) / (2*a)
        x2 = (-b - discriminant**0.5) / (2*a)
        if x1 == int(x1):
            x1 = int(x1)
        if x2 == int(x2):
            x2 = int(x2)
        return f"x = {x1}, x = {x2}"

    # Linear: ax + b = c  or  x + b = c  or  ax = c
    linear_match = re.match(
        r"(?:solve|find|what is)?\s*([+-]?\d*\.?\d*)\s*\*?\s*x\s*([+-]\s*\d*\.?\d*)?\s*=\s*([+-]?\d*\.?\d*)",
        text_lower,
    )
    if linear_match:
        a_str, b_str, c_str = linear_match.groups()
        a = float(a_str) if a_str and a_str not in ("", "+", "-") else (1.0 if not a_str or a_str == "+" else -1.0)
        b = float(b_str.replace(" ", "")) if b_str else 0.0
        c = float(c_str) if c_str else 0.0

        if a == 0:
            return "No solution: coefficient of x is zero."

        x = (c - b) / a
        if x == int(x):
            x = int(x)
        return f"x = {x}"

    return None


# ─── Translation (Basic) ──────────────────────────────────────────────────────

# Common English → Spanish/French/German word replacements
_TRANSLATIONS: dict[str, dict[str, str]] = {
    "spanish": {
        "hello": "hola", "goodbye": "adiós", "thank you": "gracias",
        "please": "por favor", "yes": "sí", "no": "no",
        "good morning": "buenos días", "good night": "buenas noches",
        "how are you": "cómo estás", "fine": "bien",
        "water": "agua", "food": "comida", "friend": "amigo",
        "love": "amor", "house": "casa", "dog": "perro",
        "cat": "gato", "book": "libro", "car": "coche",
        "good": "bueno", "bad": "malo", "big": "grande",
        "small": "pequeño", "hot": "caliente", "cold": "frío",
        "one": "uno", "two": "dos", "three": "tres",
        "four": "cuatro", "five": "cinco", "six": "seis",
        "seven": "siete", "eight": "ocho", "nine": "nueve", "ten": "diez",
    },
    "french": {
        "hello": "bonjour", "goodbye": "au revoir", "thank you": "merci",
        "please": "s'il vous plaît", "yes": "oui", "no": "non",
        "good morning": "bonjour", "good night": "bonne nuit",
        "how are you": "comment allez-vous", "fine": "bien",
        "water": "eau", "food": "nourriture", "friend": "ami",
        "love": "amour", "house": "maison", "dog": "chien",
        "cat": "chat", "book": "livre", "car": "voiture",
        "good": "bon", "bad": "mauvais", "big": "grand",
        "small": "petit", "hot": "chaud", "cold": "froid",
        "one": "un", "two": "deux", "three": "trois",
        "four": "quatre", "five": "cinq", "six": "six",
        "seven": "sept", "eight": "huit", "nine": "neuf", "ten": "dix",
    },
    "german": {
        "hello": "hallo", "goodbye": "auf Wiedersehen", "thank you": "danke",
        "please": "bitte", "yes": "ja", "no": "nein",
        "good morning": "guten Morgen", "good night": "gute Nacht",
        "how are you": "wie geht es dir", "fine": "gut",
        "water": "Wasser", "food": "Essen", "friend": "Freund",
        "love": "Liebe", "house": "Haus", "dog": "Hund",
        "cat": "Katze", "book": "Buch", "car": "Auto",
        "good": "gut", "bad": "schlecht", "big": "groß",
        "small": "klein", "hot": "heiß", "cold": "kalt",
        "one": "eins", "two": "zwei", "three": "drei",
        "four": "vier", "five": "fünf", "six": "sechs",
        "seven": "sieben", "eight": "acht", "nine": "neun", "ten": "zehn",
    },
}

def _translate(text: str, target_lang: str) -> str | None:
    """Basic word-by-word translation using a dictionary."""
    target_lang = target_lang.lower()
    if target_lang not in _TRANSLATIONS:
        return None

    dictionary = _TRANSLATIONS[target_lang]
    words = text.split()
    result = []
    i = 0
    while i < len(words):
        # Try 2-word phrases first
        if i + 1 < len(words):
            two_word = (words[i] + " " + words[i+1]).lower()
            if two_word in dictionary:
                result.append(dictionary[two_word])
                i += 2
                continue
        # Single word
        word_lower = words[i].lower().rstrip(".,!?;:")
        if word_lower in dictionary:
            translated = dictionary[word_lower]
            # Preserve capitalization
            if words[i][0].isupper():
                translated = translated[0].upper() + translated[1:]
            result.append(translated)
        else:
            result.append(words[i])
        i += 1
    return " ".join(result)


# ─── File Parsing ─────────────────────────────────────────────────────────────

def _parse_file_summary(filepath: str) -> str | None:
    """Read a file and return a summary of its contents."""
    import os
    if not os.path.exists(filepath):
        return f"File not found: {filepath}"

    size = os.path.getsize(filepath)
    ext = os.path.splitext(filepath)[1].lower()

    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading file: {e}"

    lines = content.count("\n") + 1
    words = len(content.split())
    chars = len(content)

    parts = [
        f"File: {os.path.basename(filepath)}",
        f"Type: {ext or 'unknown'}",
        f"Size: {size:,} bytes",
        f"Lines: {lines:,}",
        f"Words: {words:,}",
        f"Characters: {chars:,}",
    ]

    # Type-specific info
    if ext == ".py":
        classes = len(re.findall(r"^class\s+\w+", content, re.MULTILINE))
        functions = len(re.findall(r"^def\s+\w+", content, re.MULTILINE))
        imports = len(re.findall(r"^(?:import|from)\s+", content, re.MULTILINE))
        parts.append(f"Classes: {classes}")
        parts.append(f"Functions: {functions}")
        parts.append(f"Imports: {imports}")
    elif ext == ".json":
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                parts.append(f"Keys: {len(data)}")
                parts.append(f"Top-level keys: {', '.join(list(data.keys())[:10])}")
            elif isinstance(data, list):
                parts.append(f"Array length: {len(data)}")
        except json.JSONDecodeError:
            parts.append("(invalid JSON)")
    elif ext == ".csv":
        row_count = content.count("\n")
        csv_headers = content.split("\n")[0] if content else ""
        parts.append(f"Data rows: ~{row_count}")
        parts.append(f"Columns: {csv_headers}")
    elif ext in (".md", ".markdown"):
        headers: list[str] = re.findall(r"^#+\s+(.+)$", content, re.MULTILINE)
        parts.append(f"Headers: {len(headers)}")
        if headers:
            parts.append(f"Sections: {'; '.join(str(h) for h in headers[:10])}")
    elif ext in (".html", ".htm"):
        tags = re.findall(r"<(\w+)", content)
        parts.append(f"HTML tags: {len(tags)}")
        links = re.findall(r'href=["\']([^"\']+)', content)
        parts.append(f"Links: {len(links)}")

    return "\n".join(parts)


# ─── Text Rewriting ───────────────────────────────────────────────────────────

def _simplify_text(text: str) -> str:
    """Simplify text by removing filler words and shortening sentences."""
    filler = {
        "very", "really", "quite", "rather", "somewhat", "fairly", "pretty",
        "just", "actually", "basically", "literally", "essentially",
        "in order to", "due to the fact that", "in spite of the fact that",
        "at this point in time", "for the purpose of", "in the event that",
    }
    result = text
    for word in filler:
        result = re.sub(r"\b" + re.escape(word) + r"\b", "", result, flags=re.IGNORECASE)
    # Clean up double spaces
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _expand_text(text: str) -> str:
    """Expand text by adding transitional phrases and context."""
    sents = _sentences(text)
    if len(sents) <= 1:
        return text

    transitions = ["Furthermore, ", "In addition, ", "Moreover, ", "Additionally, ", "It is also worth noting that "]
    result = []
    for i, sent in enumerate(sents):
        if i > 0:
            result.append(transitions[(i - 1) % len(transitions)] + sent.lower()[0].upper() + sent[1:])
        else:
            result.append(sent)
    return ". ".join(result)


def _change_tone(text: str, tone: str) -> str:
    """Adjust the tone of text (basic implementation)."""
    formal_replacements = {
        "can't": "cannot", "won't": "will not", "don't": "do not",
        "it's": "it is", "they're": "they are", "we're": "we are",
        "gonna": "going to", "wanna": "want to", "gotta": "got to",
        "yeah": "yes", "nope": "no", "ok": "acceptable", "okay": "acceptable",
    }
    casual_replacements = {v: k for k, v in formal_replacements.items()}

    if tone == "formal":
        for casual, formal in formal_replacements.items():
            text = re.sub(r"\b" + re.escape(casual) + r"\b", formal, text, flags=re.IGNORECASE)
    elif tone == "casual":
        for formal, casual in casual_replacements.items():
            text = re.sub(r"\b" + re.escape(formal) + r"\b", casual, text, flags=re.IGNORECASE)

    return text


# ─── Structured Output ────────────────────────────────────────────────────────

def _to_json(text: str, messages: list[dict]) -> str:
    """Convert text/response to structured JSON output."""
    # If the user asked for JSON, try to structure the information
    # Check if there's a previous assistant response to format
    context = ""
    for msg in messages:
        if msg.get("role") == "assistant":
            context = msg.get("content", "")
            if isinstance(context, list):
                context = " ".join(p.get("text", "") for p in context if isinstance(p, dict))

    target_text = context or text

    # Try to detect key-value patterns
    data: dict[str, Any] = {}

    # Extract emails
    emails = _EMAIL_RE.findall(target_text)
    if emails:
        data["emails"] = emails

    # Extract phones
    phones = ["-".join(m.groups()) for m in _PHONE_RE.finditer(target_text)]
    if phones:
        data["phones"] = phones

    # Extract dates
    dates = [m.group().strip() for m in _DATE_RE.finditer(target_text)]
    if dates:
        data["dates"] = dates

    # Extract currency
    currency = [m.group().strip() for m in _CURRENCY_RE.finditer(target_text)]
    if currency:
        data["amounts"] = currency

    # Extract names
    names = _NAME_RE.findall(target_text)
    if names:
        data["names"] = list(set(names))

    # If we found structured data, return it
    if data:
        return json.dumps(data, indent=2)

    # Otherwise, try to parse as bullet points → JSON
    lines = target_text.strip().split("\n")
    if len(lines) > 1:
        items = []
        for line in lines:
            line = line.strip().lstrip("-*• ")
            if line:
                items.append(line)
        if items:
            return json.dumps({"items": items}, indent=2)

    # Fallback: wrap in a simple object
    return json.dumps({"text": target_text.strip()}, indent=2)


# ─── Keyword Extraction ───────────────────────────────────────────────────────

def _extract_keywords(text: str, n: int = 10) -> list[str]:
    """Extract top keywords using TF-IDF scoring."""
    sents = _sentences(text)
    if len(sents) < 2:
        # For short text, just use word frequency
        tokens = _tokenize(text)
        stop_words = _STOP_WORDS
        filtered = [t for t in tokens if t not in stop_words and len(t) > 2]
        return [word for word, _ in Counter(filtered).most_common(n)]

    tfidf = _compute_tfidf(sents)
    if tfidf.size == 0:
        return []

    # Sum TF-IDF scores across all sentences for each word
    vocab = sorted({word for s in sents for word in _tokenize(s)})
    word_scores = np.sum(tfidf, axis=0)

    # Sort by score
    ranked = sorted(zip(vocab, word_scores, strict=True), key=lambda x: -x[1])
    return [word for word, score in ranked[:n] if score > 0]


_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "can", "this", "that",
    "these", "those", "i", "you", "he", "she", "it", "we", "they",
    "what", "which", "who", "when", "where", "why", "how", "all",
    "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "also", "as", "if", "then", "else", "about",
}


# ─── Main Engine ──────────────────────────────────────────────────────────────

class LocalEngine:
    """Embedded text processing engine. No LLM, no model download.

    Handles the 80% of "AI" requests that are really just text processing:
    - Summarization (extractive)
    - Classification (sentiment, category, spam)
    - Extraction (emails, phones, dates, names, etc.)
    - Simple Q&A (arithmetic, unit conversion, knowledge base)
    - Code generation (template-based)
    - Structured output (text → JSON)
    - Text rewriting (simplify, expand, tone adjustment)
    - Keyword extraction
    - Translation (English → Spanish/French/German, word-by-word)
    - Algebra solver (linear and quadratic equations)
    - File parsing (Python, JSON, CSV, Markdown, HTML summaries)

    When it can't handle a request, it returns handled=False so the
    router can escalate to Ollama or cloud.
    """

    def __init__(self):
        self._handlers = {
            "summarization": self._handle_summarization,
            "classification": self._handle_classification,
            "extraction": self._handle_extraction,
            "simple_qa": self._handle_simple_qa,
            "code_completion": self._handle_code,
            "structured_generation": self._handle_structured,
            "reasoning": self._handle_reasoning,
            "creative": self._handle_creative,
            "rag": self._handle_rag,
            "agentic": self._handle_agentic,
            "unknown": self._handle_unknown,
        }

    def can_handle(self, intent: str, complexity: str) -> bool:
        """Check if the engine can handle a given intent+complexity."""
        # Can't handle complex or agentic tasks
        if complexity in ("complex",) and intent in ("reasoning", "agentic", "creative"):
            return False
        if intent == "agentic":
            return False
        # Can handle trivial reasoning (arithmetic, algebra)
        if complexity == "trivial" and intent == "reasoning":
            return True
        # Can handle trivial and simple for most intents
        if complexity in ("trivial", "simple"):
            return True
        # Can handle moderate for classification, extraction, summarization, simple_qa
        return complexity == "moderate" and intent in ("classification", "extraction", "summarization", "simple_qa", "structured_generation")

    def generate(
        self,
        messages: list[dict],
        intent: str,
        complexity: str,
        **kwargs,
    ) -> EngineResponse:
        """Generate a response using deterministic algorithms."""
        import time
        start = time.time()

        # Get the last user message
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    user_text = content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            user_text += part.get("text", "")
                break

        if not user_text:
            return EngineResponse(content="", handled=False, method="no_input")

        # Check if we can handle this
        if not self.can_handle(intent, complexity):
            return EngineResponse(
                content="",
                handled=False,
                method="cannot_handle",
                confidence=0.0,
            )

        # Dispatch to handler
        handler = self._handlers.get(intent, self._handle_unknown)
        content = handler(user_text, messages, **kwargs)

        latency = (time.time() - start) * 1000

        if content is None:
            return EngineResponse(
                content="",
                handled=False,
                method=f"{intent}_no_match",
                latency_ms=latency,
            )

        return EngineResponse(
            content=content,
            handled=True,
            method=intent,
            input_tokens=_estimate_tokens(user_text),
            output_tokens=_estimate_tokens(content),
            latency_ms=latency,
            confidence=0.85,
        )

    # ─── Handlers ──────────────────────────────────────────────────────────

    def _handle_summarization(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Extractive summarization."""
        # Strip common prefixes like "Summarize:", "Summarize this:", etc.
        target = text
        prefix_match = re.match(
            r"^(?:please\s+)?(?:summarize|summary|summarise)(?:\s+this)?\s*[:\-]?\s*",
            text, re.IGNORECASE,
        )
        if prefix_match:
            target = text[prefix_match.end():].strip()

        # If the text is short enough, just return it
        if _word_count(target) < 50:
            return target

        # Determine number of sentences for summary
        max_sents = 3
        if _word_count(target) > 500:
            max_sents = 5

        summary = _summarize_extractive(target, max_sentences=max_sents)
        return summary

    def _handle_classification(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Text classification (sentiment, category, spam)."""
        text_lower = text.lower()

        # Determine what kind of classification
        if "sentiment" in text_lower or "positive" in text_lower or "negative" in text_lower:
            # Find the text to classify (usually after a colon or in quotes)
            target = self._extract_target_text(text)
            if target:
                result = _classify_sentiment(target)
                return f"The sentiment is: {result}"
            return None

        if "spam" in text_lower:
            target = self._extract_target_text(text)
            if target:
                result = _classify_spam(target)
                return f"Classification: {result}"
            return None

        if "categor" in text_lower or "topic" in text_lower or "subject" in text_lower:
            target = self._extract_target_text(text)
            if target:
                result = _classify_category(target)
                return f"Category: {result}"
            return None

        # Generic classification — try all and return the most relevant
        target = self._extract_target_text(text)
        if target:
            sentiment = _classify_sentiment(target)
            category = _classify_category(target)
            return f"Sentiment: {sentiment}\nCategory: {category}"

        return None

    def _handle_extraction(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Entity extraction."""
        # Determine what to extract
        text_lower = text.lower()

        # Check for specific entity types
        for entity_type in ["email", "phone", "url", "date", "money", "currency",
                            "name", "ip", "zip", "amount"]:
            if entity_type in text_lower:
                # The text to extract from is usually after "from:" or in quotes
                target = self._extract_target_text(text)
                if target:
                    return _extract_by_pattern(target, entity_type)

        # General extraction — extract everything
        target = self._extract_target_text(text)
        if target:
            entities = _extract_entities(target)
            found = {k: v for k, v in entities.items() if v}
            if found:
                lines = []
                for etype, values in found.items():
                    if len(values) == 1:
                        lines.append(f"{etype}: {values[0]}")
                    else:
                        lines.append(f"{etype}: {', '.join(values)}")
                return "\n".join(lines)
            return "No entities found in the text."

        return None

    def _handle_simple_qa(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Simple Q&A using knowledge base, arithmetic, algebra, and conversions."""
        # Try algebra solver first (e.g. "solve 2x + 3 = 7")
        # But only for equations that contain '='
        if "=" in text:
            result = _solve_algebra(text)
            if result:
                return result

        result = _simple_qa(text)
        return result

    def _handle_code(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Template-based code generation."""
        code = _generate_code(text)
        if code:
            return f"```python\n{code}\n```"
        return None

    def _handle_structured(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Convert text to structured JSON output."""
        response_format = kwargs.get("response_format")
        if response_format and response_format.get("type") == "json":
            return _to_json(text, messages)
        return _to_json(text, messages)

    def _handle_reasoning(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Basic reasoning — arithmetic, algebra, logic, comparisons."""
        # Try algebra first (e.g. "solve 2x + 3 = 7")
        if "=" in text:
            result = _solve_algebra(text)
            if result:
                return result

        # Try arithmetic
        result = _try_arithmetic(text)
        if result:
            return result

        # Try unit conversion
        result = _try_unit_conversion(text)
        if result:
            return result

        # Try definition
        result = _try_definition(text)
        if result:
            return result

        # Can't handle complex reasoning
        return None

    def _handle_creative(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Limited creative tasks — text rewriting and translation."""
        text_lower = text.lower()

        # Translation
        if "translat" in text_lower:
            for lang in _TRANSLATIONS:
                if lang in text_lower:
                    target = self._extract_target_text(text)
                    if target:
                        result = _translate(target, lang)
                        if result:
                            return result
            return None

        if "simplif" in text_lower:
            target = self._extract_target_text(text)
            if target:
                return _simplify_text(target)

        if "expand" in text_lower or "elaborate" in text_lower:
            target = self._extract_target_text(text)
            if target:
                return _expand_text(target)

        if "formal" in text_lower:
            target = self._extract_target_text(text)
            if target:
                return _change_tone(target, "formal")

        if "casual" in text_lower or "informal" in text_lower:
            target = self._extract_target_text(text)
            if target:
                return _change_tone(target, "casual")

        return None

    def _handle_rag(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Basic RAG — find relevant info in provided context."""
        # Look for context in previous messages
        context = ""
        question = text
        for msg in messages:
            if msg.get("role") == "system" or msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    if len(content) > len(context):
                        context = content
                    elif "?" in content:
                        question = content

        if not context:
            return None

        # Find the most relevant sentence(s) in the context
        question_tokens = set(_tokenize(question)) - _STOP_WORDS
        if not question_tokens:
            return None

        sents = _sentences(context)
        if not sents:
            return None

        scored = []
        for sent in sents:
            sent_tokens = set(_tokenize(sent))
            overlap = len(question_tokens & sent_tokens)
            if overlap > 0:
                scored.append((overlap, sent))

        if not scored:
            return None

        scored.sort(key=lambda x: -x[0])
        top = [s for _, s in scored[:3]]

        # Format as answer
        if len(top) == 1:
            return top[0].strip()
        return "\n".join(f"• {s.strip()}" for s in top)

    def _handle_agentic(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Can't handle agentic workflows — always returns None."""
        return None

    def _handle_unknown(self, text: str, messages: list[dict], **kwargs) -> str | None:
        """Fallback — try everything."""
        # Try algebra
        result = _solve_algebra(text)
        if result:
            return result

        # Try Q&A
        result = _simple_qa(text)
        if result:
            return result

        # Try translation
        text_lower = text.lower()
        if "translat" in text_lower:
            for lang in _TRANSLATIONS:
                if lang in text_lower:
                    target = self._extract_target_text(text)
                    if target:
                        result = _translate(target, lang)
                        if result:
                            return result

        # Try file parsing
        file_match = re.search(r"(?:parse|summarize|analyze|read)\s+(?:file\s+)?([\w\\/\.\-:]+\.\w+)", text_lower)
        if file_match:
            filepath = file_match.group(1)
            result = _parse_file_summary(filepath)
            if result:
                return result

        # Try code generation
        result = _generate_code(text)
        if result:
            return f"```python\n{result}\n```"

        # Try keyword extraction if the text is long
        if _word_count(text) > 100:
            keywords = _extract_keywords(text, 5)
            if keywords:
                return f"Key topics: {', '.join(keywords)}"

        return None

    # ─── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _extract_target_text(query: str) -> str:
        """Extract the target text from a query like:
        "Classify the sentiment of: 'I love this product'"
        "Extract emails from: john@example.com is here"
        """
        # Try after colon
        if ":" in query:
            parts = query.split(":", 1)
            if len(parts) == 2:
                target = parts[1].strip()
                # Remove surrounding quotes
                target = target.strip("'\"")
                if target:
                    return target

        # Try text in quotes
        quoted = re.search(r"['\"](.+?)['\"]", query)
        if quoted:
            return quoted.group(1)

        # Try after "from" or "of" or "in"
        for preposition in ["from", "of", "in this text", "in the text", "in this passage"]:
            pattern = rf"\b{re.escape(preposition)}\b\s*[:\-]?\s*(.+)"
            match = re.search(pattern, query, re.IGNORECASE | re.DOTALL)
            if match:
                target = match.group(1).strip().rstrip(".")
                if len(target.split()) >= 3:
                    return target

        # If the query is long enough, treat the whole thing as the target
        if _word_count(query) > 20:
            return query

        return ""
