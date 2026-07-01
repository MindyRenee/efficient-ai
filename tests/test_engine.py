"""
Tests for the LocalEngine — embedded deterministic text processing.
"""

import pytest

from efficient.local_engine import (
    LocalEngine,
    _change_tone,
    _classify_category,
    _classify_sentiment,
    _classify_spam,
    _expand_text,
    _extract_entities,
    _extract_keywords,
    _generate_code,
    _parse_file_summary,
    _simple_qa,
    _simplify_text,
    _solve_algebra,
    _summarize_extractive,
    _to_json,
    _translate,
    _try_arithmetic,
    _try_definition,
    _try_unit_conversion,
)


class TestSummarization:
    def test_short_text_returned_as_is(self):
        text = "This is a short text that doesn't need summarization."
        result = _summarize_extractive(text, max_sentences=3)
        assert result == text.strip()

    def test_long_text_summarized(self):
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is an important sentence about machine learning and AI. "
            "Another sentence discusses data centers and their environmental impact. "
            "The weather today is sunny with a high of 75 degrees. "
            "Quantum computing represents a paradigm shift in computational capability. "
            "Renewable energy adoption is accelerating globally. "
            "The stock market showed mixed results this quarter. "
            "Climate change remains a pressing global challenge."
        )
        result = _summarize_extractive(text, max_sentences=2)
        assert len(result) < len(text)
        assert result.count(".") <= 3

    def test_single_sentence(self):
        text = "Only one sentence here."
        result = _summarize_extractive(text, max_sentences=3)
        assert "Only one sentence here" in result


class TestSentimentClassification:
    def test_positive(self):
        assert _classify_sentiment("I absolutely love this product, it's amazing!") == "positive"

    def test_negative(self):
        assert _classify_sentiment("This is terrible and awful, I hate it.") == "negative"

    def test_neutral(self):
        assert _classify_sentiment("The meeting is scheduled for Tuesday.") == "neutral"

    def test_mixed_neutral(self):
        assert _classify_sentiment("Good and bad parts alike.") == "neutral"


class TestCategoryClassification:
    def test_technology(self):
        assert (
            _classify_category("The software uses machine learning algorithms to process data.")
            == "technology"
        )

    def test_business(self):
        assert (
            _classify_category("The company's revenue and profit growth this quarter.")
            == "business"
        )

    def test_science(self):
        assert (
            _classify_category("The research study experiments with quantum physics.") == "science"
        )

    def test_general(self):
        assert _classify_category("Hello world") == "general"


class TestSpamClassification:
    def test_spam(self):
        assert _classify_spam("FREE!!! WINNER!! Click here NOW for CASH prize!!!") == "spam"

    def test_not_spam(self):
        assert _classify_spam("Hi John, can we schedule a meeting for Tuesday?") == "not spam"


class TestEntityExtraction:
    def test_email_extraction(self):
        entities = _extract_entities("Contact me at john@example.com or jane@test.org")
        assert "john@example.com" in entities["emails"]
        assert "jane@test.org" in entities["emails"]

    def test_phone_extraction(self):
        entities = _extract_entities("Call me at 555-123-4567")
        assert len(entities["phones"]) == 1

    def test_url_extraction(self):
        entities = _extract_entities("Visit https://example.com for more info")
        assert "https://example.com" in entities["urls"]

    def test_date_extraction(self):
        entities = _extract_entities("The event is on January 15, 2024")
        assert len(entities["dates"]) >= 1

    def test_currency_extraction(self):
        entities = _extract_entities("The price is $1,299.99")
        assert len(entities["currency"]) >= 1

    def test_no_entities(self):
        entities = _extract_entities("Just a regular sentence with nothing special.")
        assert not entities["emails"]
        assert not entities["phones"]


class TestSimpleQA:
    def test_arithmetic_addition(self):
        result = _try_arithmetic("what is 2 + 2")
        assert result is not None
        assert "4" in result

    def test_arithmetic_multiplication(self):
        result = _try_arithmetic("calculate 7 * 8")
        assert result is not None
        assert "56" in result

    def test_arithmetic_division(self):
        result = _try_arithmetic("what is 100 / 4")
        assert result is not None
        assert "25" in result

    def test_arithmetic_complex(self):
        result = _try_arithmetic("(2 + 3) * 4")
        assert result is not None
        assert "20" in result

    def test_unit_conversion(self):
        result = _try_unit_conversion("convert 100 feet to meters")
        assert result is not None
        assert "30.48" in result

    def test_unit_conversion_celsius(self):
        result = _try_unit_conversion("convert 0 celsius to fahrenheit")
        assert result is not None
        assert "32" in result

    def test_definition_capital(self):
        result = _try_definition("What is the capital of France?")
        assert result is not None
        assert "Paris" in result

    def test_definition_pi(self):
        result = _try_definition("What is pi?")
        assert result is not None
        assert "3.14" in result

    def test_definition_unknown(self):
        result = _try_definition("What is a flibbertigibbet?")
        assert result is None

    def test_simple_qa_arithmetic(self):
        result = _simple_qa("what is 5 + 3")
        assert result is not None
        assert "8" in result

    def test_simple_qa_knowledge(self):
        result = _simple_qa("What is the capital of Japan?")
        assert result is not None
        assert "Tokyo" in result

    def test_simple_qa_unknown(self):
        result = _simple_qa("What is the meaning of consciousness?")
        assert result is None


class TestCodeGeneration:
    def test_factorial(self):
        code = _generate_code("write a function to calculate factorial")
        assert code is not None
        assert "def factorial" in code
        assert "n * factorial" in code

    def test_fibonacci(self):
        code = _generate_code("generate fibonacci sequence")
        assert code is not None
        assert "def fibonacci" in code

    def test_palindrome(self):
        code = _generate_code("check if a string is a palindrome")
        assert code is not None
        assert "def is_palindrome" in code

    def test_prime(self):
        code = _generate_code("write a prime number checker")
        assert code is not None
        assert "def is_prime" in code

    def test_hello_world(self):
        code = _generate_code("write hello world")
        assert code is not None
        assert "Hello, World" in code

    def test_rest_api(self):
        code = _generate_code("create a REST API with flask")
        assert code is not None
        assert "Flask" in code
        assert "route" in code

    def test_binary_search(self):
        code = _generate_code("implement binary search")
        assert code is not None
        assert "def binary_search" in code

    def test_unknown_pattern(self):
        code = _generate_code("write a quantum entanglement simulator")
        assert code is None


class TestTextRewriting:
    def test_simplify(self):
        text = "This is very really quite simply just a test."
        result = _simplify_text(text)
        assert "very" not in result
        assert "really" not in result

    def test_expand(self):
        text = "The first point is about data. The second point covers machine learning. The third point discusses optimization."
        result = _expand_text(text)
        assert "Furthermore" in result or "In addition" in result or "Moreover" in result

    def test_formal_tone(self):
        text = "I can't do it, it's not gonna work."
        result = _change_tone(text, "formal")
        assert "cannot" in result
        assert "it is" in result

    def test_casual_tone(self):
        text = "I cannot do it, it is not going to work."
        result = _change_tone(text, "casual")
        assert "can't" in result or "it's" in result


class TestKeywordExtraction:
    def test_extract_keywords(self):
        text = (
            "Machine learning is a subset of artificial intelligence. "
            "Machine learning algorithms learn from data. "
            "Artificial intelligence transforms industries."
        )
        keywords = _extract_keywords(text, n=5)
        assert len(keywords) <= 5
        assert len(keywords) > 0

    def test_keywords_short_text(self):
        keywords = _extract_keywords("The quick brown fox", n=3)
        assert len(keywords) <= 3


class TestStructuredOutput:
    def test_json_with_entities(self):
        text = "Contact John at john@example.com or call 555-123-4567"
        result = _to_json(text, [])
        import json

        data = json.loads(result)
        assert "emails" in data or "phones" in data

    def test_json_fallback(self):
        text = "Just some plain text without entities"
        result = _to_json(text, [])
        import json

        data = json.loads(result)
        assert "text" in data


class TestLocalEngine:
    @pytest.fixture
    def engine(self):
        return LocalEngine()

    def test_can_handle_trivial(self, engine):
        assert engine.can_handle("simple_qa", "trivial")
        assert engine.can_handle("classification", "trivial")
        assert engine.can_handle("extraction", "trivial")
        assert engine.can_handle("summarization", "trivial")

    def test_can_handle_simple(self, engine):
        assert engine.can_handle("simple_qa", "simple")
        assert engine.can_handle("code_completion", "simple")
        assert engine.can_handle("classification", "simple")

    def test_cannot_handle_agentic(self, engine):
        assert not engine.can_handle("agentic", "simple")
        assert not engine.can_handle("agentic", "complex")

    def test_cannot_handle_complex_reasoning(self, engine):
        assert not engine.can_handle("reasoning", "complex")
        assert not engine.can_handle("creative", "complex")

    def test_generate_summarization(self, engine):
        text = (
            "Machine learning is a field of artificial intelligence. "
            "It uses statistical methods to learn from data. "
            "Deep learning is a subset of machine learning. "
            "Neural networks are the backbone of deep learning. "
            "These technologies power modern AI applications."
        )
        result = engine.generate(
            messages=[{"role": "user", "content": f"Summarize: {text}"}],
            intent="summarization",
            complexity="simple",
        )
        assert result.handled
        assert len(result.content) > 0
        assert result.method == "summarization"

    def test_generate_classification(self, engine):
        result = engine.generate(
            messages=[
                {"role": "user", "content": "Classify the sentiment of: 'I love this product!'"}
            ],
            intent="classification",
            complexity="simple",
        )
        assert result.handled
        assert "positive" in result.content

    def test_generate_extraction(self, engine):
        result = engine.generate(
            messages=[
                {"role": "user", "content": "Extract the email from: Contact john@example.com"}
            ],
            intent="extraction",
            complexity="simple",
        )
        assert result.handled
        assert "john@example.com" in result.content

    def test_generate_simple_qa(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "What is 2 + 2?"}],
            intent="simple_qa",
            complexity="trivial",
        )
        assert result.handled
        assert "4" in result.content

    def test_generate_code(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "Write a Python function for factorial"}],
            intent="code_completion",
            complexity="simple",
        )
        assert result.handled
        assert "def factorial" in result.content

    def test_generate_cannot_handle(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "Plan a multi-step agentic workflow"}],
            intent="agentic",
            complexity="complex",
        )
        assert not result.handled

    def test_generate_unknown_fallback_arithmetic(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "What is 10 * 10?"}],
            intent="unknown",
            complexity="trivial",
        )
        assert result.handled
        assert "100" in result.content

    def test_latency_is_low(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "What is the capital of France?"}],
            intent="simple_qa",
            complexity="trivial",
        )
        assert result.latency_ms < 100  # Should be well under 100ms

    def test_rag_basic(self, engine):
        messages = [
            {
                "role": "system",
                "content": "The revenue for Q3 2024 was $5.2 million, up 15% from Q2. The company employs 250 people across three offices.",
            },
            {"role": "user", "content": "What was the revenue for Q3?"},
        ]
        result = engine.generate(
            messages=messages,
            intent="rag",
            complexity="simple",
        )
        assert result.handled
        assert "revenue" in result.content.lower() or "5.2" in result.content


class TestAlgebraSolver:
    def test_linear_simple(self):
        result = _solve_algebra("2x + 3 = 7")
        assert result is not None
        assert "x = 2" in result

    def test_linear_no_constant(self):
        result = _solve_algebra("3x = 15")
        assert result is not None
        assert "x = 5" in result

    def test_linear_with_solve_prefix(self):
        result = _solve_algebra("solve 2x + 10 = 20")
        assert result is not None
        assert "x = 5" in result

    def test_linear_negative(self):
        result = _solve_algebra("x - 5 = 3")
        assert result is not None
        assert "x = 8" in result

    def test_quadratic_two_roots(self):
        result = _solve_algebra("x^2 - 5x + 6 = 0")
        assert result is not None
        assert "x = 2" in result or "x = 3" in result

    def test_quadratic_double_root(self):
        result = _solve_algebra("x^2 - 4x + 4 = 0")
        assert result is not None
        assert "double root" in result

    def test_quadratic_complex(self):
        result = _solve_algebra("x^2 + 1 = 0")
        assert result is not None
        assert "complex" in result

    def test_not_equation(self):
        result = _solve_algebra("hello world")
        assert result is None


class TestTranslation:
    def test_spanish_hello(self):
        result = _translate("hello", "spanish")
        assert result == "hola"

    def test_french_thank_you(self):
        result = _translate("thank you", "french")
        assert result == "merci"

    def test_german_yes(self):
        result = _translate("yes", "german")
        assert result == "ja"

    def test_spanish_sentence(self):
        result = _translate("hello and goodbye", "spanish")
        assert "hola" in result
        assert "adiós" in result

    def test_unsupported_language(self):
        result = _translate("hello", "japanese")
        assert result is None

    def test_preserves_untranslated_words(self):
        result = _translate("hello world", "spanish")
        assert "hola" in result
        assert "world" in result  # "world" not in dictionary, kept as-is


class TestFileParsing:
    def test_parse_python_file(self, tmp_path):
        filepath = tmp_path / "test.py"
        filepath.write_text(
            "import os\n"
            "from typing import List\n"
            "\n"
            "class Foo:\n"
            "    def bar(self):\n"
            "        pass\n"
            "\n"
            "def baz():\n"
            "    return 42\n"
        )
        result = _parse_file_summary(str(filepath))
        assert result is not None
        assert "test.py" in result
        assert ".py" in result
        assert "Classes: 1" in result
        assert "Functions: 1" in result
        assert "Imports: 2" in result

    def test_parse_json_file(self, tmp_path):
        filepath = tmp_path / "data.json"
        filepath.write_text('{"name": "test", "value": 42}')
        result = _parse_file_summary(str(filepath))
        assert result is not None
        assert "Keys: 2" in result

    def test_parse_csv_file(self, tmp_path):
        filepath = tmp_path / "data.csv"
        filepath.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA")
        result = _parse_file_summary(str(filepath))
        assert result is not None
        assert "Columns:" in result
        assert "name" in result

    def test_parse_markdown_file(self, tmp_path):
        filepath = tmp_path / "doc.md"
        filepath.write_text("# Title\n\n## Section 1\n\nSome text.\n\n## Section 2\n")
        result = _parse_file_summary(str(filepath))
        assert result is not None
        assert "Headers: 3" in result

    def test_file_not_found(self):
        result = _parse_file_summary("/nonexistent/file.xyz")
        assert "not found" in result.lower()


class TestExpandedCodeTemplates:
    def test_merge_sort(self):
        code = _generate_code("write a merge sort function")
        assert code is not None
        assert "def merge_sort" in code
        assert "def merge" in code

    def test_quick_sort(self):
        code = _generate_code("implement quicksort")
        assert code is not None
        assert "def quicksort" in code

    def test_hash_table(self):
        code = _generate_code("implement a hash table")
        assert code is not None
        assert "class HashTable" in code

    def test_bfs(self):
        code = _generate_code("write a bfs traversal")
        assert code is not None
        assert "def bfs" in code

    def test_dfs(self):
        code = _generate_code("implement depth first search")
        assert code is not None
        assert "def dfs" in code

    def test_binary_tree(self):
        code = _generate_code("binary tree traversal")
        assert code is not None
        assert "TreeNode" in code
        assert "inorder" in code

    def test_decorator(self):
        code = _generate_code("write a decorator")
        assert code is not None
        assert "def timing" in code or "functools" in code

    def test_dataclass(self):
        code = _generate_code("create a dataclass")
        assert code is not None
        assert "@dataclass" in code

    def test_singleton(self):
        code = _generate_code("implement singleton pattern")
        assert code is not None
        assert "Singleton" in code
        assert "_instance" in code

    def test_factory_pattern(self):
        code = _generate_code("implement factory pattern")
        assert code is not None
        assert "Factory" in code

    def test_gcd(self):
        code = _generate_code("write a gcd function")
        assert code is not None
        assert "def gcd" in code

    def test_fizzbuzz(self):
        code = _generate_code("write fizzbuzz")
        assert code is not None
        assert "def fizzbuzz" in code
        assert "Fizz" in code

    def test_matrix_multiply(self):
        code = _generate_code("matrix multiplication")
        assert code is not None
        assert "def matrix_multiply" in code

    def test_password_generator(self):
        code = _generate_code("generate a password")
        assert code is not None
        assert "def generate_password" in code

    def test_retry_decorator(self):
        code = _generate_code("write a retry decorator")
        assert code is not None
        assert "def retry" in code


class TestExpandedKnowledgeBase:
    @pytest.fixture
    def engine(self):
        return LocalEngine()

    def test_who_invented_python(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "Who invented Python?"}],
            intent="simple_qa",
            complexity="trivial",
        )
        assert result.handled
        assert "Guido" in result.content

    def test_what_is_machine_learning(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "What is machine learning?"}],
            intent="simple_qa",
            complexity="trivial",
        )
        assert result.handled
        assert "machine learning" in result.content.lower()

    def test_capital_of_south_korea(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "What is the capital of South Korea?"}],
            intent="simple_qa",
            complexity="trivial",
        )
        assert result.handled
        assert "Seoul" in result.content

    def test_golden_ratio(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "What is the golden ratio?"}],
            intent="simple_qa",
            complexity="trivial",
        )
        assert result.handled
        assert "1.618" in result.content

    def test_absolute_zero(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "What is absolute zero?"}],
            intent="simple_qa",
            complexity="trivial",
        )
        assert result.handled
        assert "0 Kelvin" in result.content or "-273" in result.content


class TestEngineIntegrationNew:
    @pytest.fixture
    def engine(self):
        return LocalEngine()

    def test_algebra_via_engine(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "Solve 2x + 3 = 7"}],
            intent="simple_qa",
            complexity="trivial",
        )
        assert result.handled
        assert "x = 2" in result.content

    def test_translation_via_engine(self, engine):
        result = engine.generate(
            messages=[{"role": "user", "content": "Translate to Spanish: hello and goodbye"}],
            intent="creative",
            complexity="simple",
        )
        assert result.handled
        assert "hola" in result.content.lower()

    def test_file_parsing_via_engine(self, engine, tmp_path):
        filepath = tmp_path / "test.py"
        filepath.write_text("def foo():\n    return 1\n")
        result = engine.generate(
            messages=[{"role": "user", "content": f"Parse file {filepath}"}],
            intent="unknown",
            complexity="simple",
        )
        assert result.handled
        assert "test.py" in result.content
