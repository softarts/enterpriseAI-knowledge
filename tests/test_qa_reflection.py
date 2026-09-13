"""
tests/test_qa_reflection.py — Unit tests for the QA Reflection stage.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure test runs even in environments where langchain/chromadb are not installed
for mod_name in [
    "yaml",
    "langchain_core",
    "langchain_core.output_parsers",
    "langchain_core.prompts",
    "langchain_openai",
    "chromadb",
    "embedding_service",
    "embedding_service.embedder",
    "vector_service",
    "vector_service.chroma_store",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


from qa_service.models import AnswerResult, RetrievedChunk
from qa_service.prompt_builder import build_reflection_prompt, REFLECTION_PROMPT_TEMPLATE
from qa_service.reflection import parse_decision, reflect
from qa_service import pipeline



class TestPromptBuilder(unittest.TestCase):
    def test_build_reflection_prompt_basic(self):
        question = "What is the capital of France?"
        context = "France is a country in Europe. Paris is its capital."
        answer = "The capital of France is Paris."

        prompt = build_reflection_prompt(question, context, answer)
        self.assertIn("Question:\nWhat is the capital of France?", prompt)
        self.assertIn("Retrieved Context:\nFrance is a country in Europe. Paris is its capital.", prompt)
        self.assertIn("Generated Answer:\nThe capital of France is Paris.", prompt)
        self.assertIn("Decision: PASS or REVISE", prompt)

    def test_build_reflection_prompt_with_curly_braces(self):
        # Context and answer containing curly braces must not cause formatting issues
        question = "How to configure JSON?"
        context = 'Use config format: {"key": "{value}", "nested": {1: 2}}'
        answer = 'Here is the JSON: {"key": "{value}"}'

        prompt = build_reflection_prompt(question, context, answer)
        self.assertIn('{"key": "{value}", "nested": {1: 2}}', prompt)
        self.assertIn('{"key": "{value}"}', prompt)


class TestDecisionParsing(unittest.TestCase):
    def test_parse_decision_pass(self):
        output = (
            "Decision: PASS\n\n"
            "Reasons:\n- Accurate.\n\n"
            "Unnecessary or out-of-scope content:\n- None\n\n"
            "Missing important information:\n- None\n\n"
            "Unsupported claims:\n- None"
        )
        self.assertEqual(parse_decision(output), "PASS")

    def test_parse_decision_revise(self):
        output = (
            "Decision: REVISE\n\n"
            "Reasons:\n- Missing key details.\n\n"
            "Unnecessary or out-of-scope content:\n- None\n\n"
            "Missing important information:\n- Step 3 is omitted.\n\n"
            "Unsupported claims:\n- None"
        )
        self.assertEqual(parse_decision(output), "REVISE")

    def test_parse_decision_case_insensitive(self):
        output = "decision: pass\nReasons: all good"
        self.assertEqual(parse_decision(output), "PASS")

    def test_parse_decision_markdown_bold(self):
        self.assertEqual(parse_decision("**Decision:** PASS\nReasons:..."), "PASS")
        self.assertEqual(parse_decision("**Decision:** **PASS**\nReasons:..."), "PASS")
        self.assertEqual(parse_decision("Decision: **REVISE**\nReasons:..."), "REVISE")
        self.assertEqual(parse_decision("**Decision**: REVISE\nReasons:..."), "REVISE")

    def test_parse_decision_none_on_invalid_or_empty(self):
        self.assertIsNone(parse_decision(""))
        self.assertIsNone(parse_decision("I think this answer is mostly good."))



class TestReflectionExecution(unittest.TestCase):
    @patch("qa_service.reflection.llm_client.generate_reflection")
    def test_reflect_pass(self, mock_generate):
        mock_output = (
            "Decision: PASS\n\n"
            "Reasons:\n- The answer directly matches retrieved context.\n\n"
            "Unnecessary or out-of-scope content:\n- None\n\n"
            "Missing important information:\n- None\n\n"
            "Unsupported claims:\n- None"
        )
        mock_generate.return_value = mock_output

        draft = "Paris is the capital of France."
        result = reflect(
            question="What is the capital of France?",
            context="Paris is the capital of France.",
            draft_answer=draft,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.decision, "PASS")
        self.assertIsNone(result.error)
        self.assertEqual(result.raw_output, mock_output)
        self.assertEqual(result.final_answer, f"{draft}\n\nReflection Note:\n{mock_output.strip()}")
        self.assertIsNotNone(result.duration_ms)
        self.assertIn("model", result.model_config)

    @patch("qa_service.reflection.llm_client.generate_reflection")
    def test_reflect_revise_does_not_modify_original_answer(self, mock_generate):
        mock_output = (
            "Decision: REVISE\n\n"
            "Reasons:\n- The answer has unsupported claims.\n\n"
            "Unnecessary or out-of-scope content:\n- Extra commentary.\n\n"
            "Missing important information:\n- None\n\n"
            "Unsupported claims:\n- France has 200 regions."
        )
        mock_generate.return_value = mock_output

        draft = "Paris is the capital of France. France has 200 regions."
        result = reflect(
            question="What is the capital of France?",
            context="Paris is the capital of France.",
            draft_answer=draft,
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.decision, "REVISE")
        self.assertIsNone(result.error)
        # Original draft answer must be preserved verbatim at start of final_answer
        self.assertTrue(result.final_answer.startswith(draft))
        self.assertEqual(result.final_answer, f"{draft}\n\nReflection Note:\n{mock_output.strip()}")

    @patch("qa_service.reflection.llm_client.generate_reflection")
    def test_reflect_handles_exception_gracefully(self, mock_generate):
        mock_generate.side_effect = RuntimeError("Connection timed out to LLM provider")

        draft = "Some draft answer"
        result = reflect(
            question="Question?",
            context="Context",
            draft_answer=draft,
        )

        self.assertIsNone(result.passed)
        self.assertEqual(result.decision, "ERROR")
        self.assertIn("RuntimeError", result.error)
        self.assertEqual(result.final_answer, f"{draft}\n\nReflection Note:\nReflection unavailable.")
        self.assertEqual(result.notes, "Reflection unavailable.")

    @patch("qa_service.reflection.llm_client.generate_reflection")
    def test_reflect_handles_empty_output(self, mock_generate):
        mock_generate.return_value = "   \n  "

        draft = "Some draft answer"
        result = reflect(
            question="Question?",
            context="Context",
            draft_answer=draft,
        )

        self.assertIsNone(result.passed)
        self.assertIsNone(result.decision)
        self.assertIn("empty", result.error)
        self.assertEqual(result.final_answer, f"{draft}\n\nReflection Note:\nReflection unavailable.")


class TestPipelineReflectionIntegration(unittest.TestCase):
    @patch("qa_service.pipeline.retrieval.retrieve")
    @patch("qa_service.pipeline.retrieval.is_confident")
    @patch("qa_service.pipeline.llm_client.generate")
    @patch("qa_service.pipeline.reflection.reflect")
    def test_pipeline_records_reflection_in_trace(
        self, mock_reflect, mock_generate, mock_is_confident, mock_retrieve
    ):
        mock_chunk = RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            title="Title",
            heading=None,
            source_path="doc.md",
            text="Document content",
            distance=0.1,
            rank=1,
        )
        mock_retrieve.return_value = [mock_chunk]
        mock_is_confident.return_value = True
        mock_generate.return_value = "Generated answer draft."

        from qa_service.models import ReflectionResult
        mock_reflect_res = ReflectionResult(
            passed=True,
            final_answer="Generated answer draft.\n\nReflection Note:\nDecision: PASS",
            notes="Decision: PASS",
            decision="PASS",
            raw_output="Decision: PASS",
            error=None,
            duration_ms=45.6,
            prompt="Prompt content",
            model="test-model",
            model_config={"model": "test-model"},
        )
        mock_reflect.return_value = mock_reflect_res

        result = pipeline.answer_question("How does it work?")

        self.assertEqual(result.answer, "Generated answer draft.\n\nReflection Note:\nDecision: PASS")
        self.assertTrue(result.passed_reflection)
        self.assertEqual(result.sources, ["chunk-1"])

        # Check trace
        steps = {step["name"]: step for step in result.trace["steps"]}
        self.assertIn("reflection", steps)
        refl_step = steps["reflection"]
        self.assertEqual(refl_step["status"], "ok")
        self.assertEqual(refl_step["duration_ms"], 45.6)

        detail = refl_step["detail"]
        self.assertEqual(detail["decision"], "PASS")
        self.assertEqual(detail["model"], "test-model")
        self.assertEqual(detail["prompt"], "Prompt content")
        self.assertEqual(detail["output"], "Decision: PASS")
        self.assertIsNone(detail["error"])
        self.assertEqual(detail["input"]["question"], "How does it work?")
        self.assertEqual(detail["input"]["answer"], "Generated answer draft.")

    @patch("qa_service.pipeline.retrieval.retrieve")
    @patch("qa_service.pipeline.retrieval.is_confident")
    @patch("qa_service.pipeline.llm_client.generate")
    @patch("qa_service.pipeline.reflection.reflect")
    def test_pipeline_reflection_error_records_trace_error(
        self, mock_reflect, mock_generate, mock_is_confident, mock_retrieve
    ):
        mock_chunk = RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            title="Title",
            heading=None,
            source_path="doc.md",
            text="Document content",
            distance=0.1,
            rank=1,
        )
        mock_retrieve.return_value = [mock_chunk]
        mock_is_confident.return_value = True
        mock_generate.return_value = "Generated answer draft."

        from qa_service.models import ReflectionResult
        mock_reflect_res = ReflectionResult(
            passed=None,
            final_answer="Generated answer draft.\n\nReflection Note:\nReflection unavailable.",
            notes="Reflection unavailable.",
            decision="ERROR",
            raw_output="",
            error="ConnectionError: unreachable",
            duration_ms=12.3,
            prompt="Prompt content",
            model="test-model",
            model_config={"model": "test-model"},
        )
        mock_reflect.return_value = mock_reflect_res

        result = pipeline.answer_question("How does it work?")

        self.assertEqual(
            result.answer,
            "Generated answer draft.\n\nReflection Note:\nReflection unavailable.",
        )
        self.assertIsNone(result.passed_reflection)

        steps = {step["name"]: step for step in result.trace["steps"]}
        self.assertIn("reflection", steps)
        refl_step = steps["reflection"]
        self.assertEqual(refl_step["status"], "error")
        self.assertEqual(refl_step["detail"]["status"], "error")
        self.assertEqual(refl_step["detail"]["decision"], "ERROR")
        self.assertEqual(refl_step["detail"]["error"], "ConnectionError: unreachable")

    @patch("qa_service.pipeline.reflection.reflect")
    def test_pipeline_empty_question_skips_reflection(self, mock_reflect):
        result = pipeline.answer_question("")
        self.assertEqual(result.answer, pipeline._NOT_FOUND_ANSWER)
        self.assertIsNone(result.passed_reflection)
        mock_reflect.assert_not_called()
        step_names = [s["name"] for s in result.trace["steps"]]
        self.assertNotIn("reflection", step_names)

    @patch("qa_service.pipeline.retrieval.retrieve")
    @patch("qa_service.pipeline.retrieval.is_confident")
    @patch("qa_service.pipeline.reflection.reflect")
    def test_pipeline_low_confidence_skips_reflection(
        self, mock_reflect, mock_is_confident, mock_retrieve
    ):
        mock_retrieve.return_value = []
        mock_is_confident.return_value = False
        result = pipeline.answer_question("Unknown question?")
        self.assertEqual(result.answer, pipeline._NOT_FOUND_ANSWER)
        self.assertIsNone(result.passed_reflection)
        mock_reflect.assert_not_called()
        step_names = [s["name"] for s in result.trace["steps"]]
        self.assertNotIn("reflection", step_names)



if __name__ == "__main__":
    unittest.main()
