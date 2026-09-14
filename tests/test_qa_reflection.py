"""
tests/test_qa_reflection.py — Unit tests for the Closed-Loop QA Reflection & Revision pipeline.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure tests run even in environments where langchain/chromadb are not installed
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


from qa_service import config, pipeline, prompt_builder, reflection, revision
from qa_service.models import AnswerResult, ParsedReflection, ReflectionResult, RetrievedChunk, RevisionResult


class TestPromptBuilder(unittest.TestCase):
    def test_build_reflection_prompt_basic(self):
        question = "What is the capital of France?"
        context = "France is a country in Europe. Paris is its capital."
        answer = "The capital of France is Paris."

        prompt = prompt_builder.build_reflection_prompt(question, context, answer)
        self.assertIn("Question:\nWhat is the capital of France?", prompt)
        self.assertIn("Retrieved Context:\nFrance is a country in Europe. Paris is its capital.", prompt)
        self.assertIn("Generated Answer:\nThe capital of France is Paris.", prompt)
        self.assertIn("Decision: PASS or REVISE", prompt)

    def test_build_reflection_prompt_with_curly_braces(self):
        question = "How to configure JSON?"
        context = 'Use config format: {"key": "{value}", "nested": {1: 2}}'
        answer = 'Here is the JSON: {"key": "{value}"}'

        prompt = prompt_builder.build_reflection_prompt(question, context, answer)
        self.assertIn('{"key": "{value}", "nested": {1: 2}}', prompt)
        self.assertIn('{"key": "{value}"}', prompt)

    def test_build_revision_prompt(self):
        question = "Explain ASC 606 step 4."
        context = "Step 4 is allocating the transaction price to distinct obligations."
        draft = "Step 4 is about revenue."
        feedback = "Decision: REVISE\nMissing important information:\n- Allocation of transaction price."

        prompt = prompt_builder.build_revision_prompt(question, context, draft, feedback)
        self.assertIn("Question:\nExplain ASC 606 step 4.", prompt)
        self.assertIn(context, prompt)
        self.assertIn("Draft Answer:\nStep 4 is about revenue.", prompt)
        self.assertIn("Reflection Feedback:\n" + feedback, prompt)
        self.assertIn("Revision Rules:", prompt)


class TestDecisionAndOutputParsing(unittest.TestCase):
    def test_parse_decision_basic(self):
        self.assertEqual(reflection.parse_decision("Decision: PASS\nReasons: ok"), "PASS")
        self.assertEqual(reflection.parse_decision("Decision: REVISE\nReasons: issues"), "REVISE")
        self.assertEqual(reflection.parse_decision("decision: pass"), "PASS")
        self.assertEqual(reflection.parse_decision("decision: revise"), "REVISE")

    def test_parse_decision_markdown_bold(self):
        self.assertEqual(reflection.parse_decision("**Decision:** PASS"), "PASS")
        self.assertEqual(reflection.parse_decision("**Decision:** **PASS**"), "PASS")
        self.assertEqual(reflection.parse_decision("Decision: **REVISE**"), "REVISE")
        self.assertEqual(reflection.parse_decision("**Decision**: REVISE"), "REVISE")

    def test_parse_decision_none_on_invalid(self):
        self.assertIsNone(reflection.parse_decision(""))
        self.assertIsNone(reflection.parse_decision("The answer looks mostly good."))

    def test_parse_reflection_output_structure(self):
        raw_output = (
            "Decision: REVISE\n\n"
            "Reasons:\n"
            "- Scope too broad\n"
            "- Missing price allocation\n\n"
            "Unnecessary or out-of-scope content:\n"
            "- Net30 payment terms are irrelevant\n\n"
            "Missing important information:\n"
            "- Step 4 allocation mechanism\n\n"
            "Unsupported claims:\n"
            "- France has 200 departments\n"
        )
        parsed = reflection.parse_reflection_output(raw_output)
        self.assertEqual(parsed.decision, "REVISE")
        self.assertEqual(parsed.reasons, ["Scope too broad", "Missing price allocation"])
        self.assertEqual(parsed.unnecessary_content, ["Net30 payment terms are irrelevant"])
        self.assertEqual(parsed.missing_information, ["Step 4 allocation mechanism"])
        self.assertEqual(parsed.unsupported_claims, ["France has 200 departments"])

        d = parsed.to_dict()
        self.assertEqual(d["decision"], "REVISE")
        self.assertEqual(len(d["reasons"]), 2)

    def test_parse_reflection_output_with_none_bullets(self):
        raw_output = (
            "Decision: PASS\n\n"
            "Reasons:\n"
            "- Completely accurate\n\n"
            "Unnecessary or out-of-scope content:\n"
            "- None\n\n"
            "Missing important information:\n"
            "- None\n\n"
            "Unsupported claims:\n"
            "- None\n"
        )
        parsed = reflection.parse_reflection_output(raw_output)
        self.assertEqual(parsed.decision, "PASS")
        self.assertEqual(parsed.reasons, ["Completely accurate"])
        self.assertEqual(parsed.unnecessary_content, [])
        self.assertEqual(parsed.missing_information, [])
        self.assertEqual(parsed.unsupported_claims, [])


class TestReflectionExecution(unittest.TestCase):
    @patch("qa_service.reflection.llm_client.generate_reflection")
    def test_reflect_pass(self, mock_generate):
        mock_output = (
            "Decision: PASS\n\n"
            "Reasons:\n- Grounded and concise\n\n"
            "Unnecessary or out-of-scope content:\n- None\n\n"
            "Missing important information:\n- None\n\n"
            "Unsupported claims:\n- None"
        )
        mock_generate.return_value = mock_output

        draft = "Paris is the capital of France."
        res = reflection.reflect("Question?", "Context", draft)
        self.assertEqual(res.status, "success")
        self.assertTrue(res.passed)
        self.assertEqual(res.decision, "PASS")
        self.assertEqual(res.final_answer, draft)
        self.assertIsNotNone(res.parsed_result)
        self.assertEqual(res.parsed_result.reasons, ["Grounded and concise"])
        self.assertIsNone(res.error)

    @patch("qa_service.reflection.llm_client.generate_reflection")
    def test_reflect_revise(self, mock_generate):
        mock_output = (
            "Decision: REVISE\n\n"
            "Reasons:\n- Extra details\n\n"
            "Unnecessary or out-of-scope content:\n- Extra info\n\n"
            "Missing important information:\n- None\n\n"
            "Unsupported claims:\n- None"
        )
        mock_generate.return_value = mock_output

        draft = "Paris is the capital of France. Extra info."
        res = reflection.reflect("Question?", "Context", draft)
        self.assertEqual(res.status, "success")
        self.assertFalse(res.passed)
        self.assertEqual(res.decision, "REVISE")
        self.assertEqual(res.final_answer, draft)

    @patch("qa_service.reflection.llm_client.generate_reflection")
    def test_reflect_handles_exception_gracefully(self, mock_generate):
        mock_generate.side_effect = TimeoutError("Connection to LLM timed out")

        draft = "Draft answer"
        res = reflection.reflect("Question?", "Context", draft)
        self.assertEqual(res.status, "error")
        self.assertIsNone(res.passed)
        self.assertIsNone(res.decision)
        self.assertIn("TimeoutError", res.error)
        self.assertEqual(res.final_answer, draft)

    @patch("qa_service.reflection.llm_client.generate_reflection")
    def test_reflect_handles_empty_output(self, mock_generate):
        mock_generate.return_value = "   \n"

        draft = "Draft answer"
        res = reflection.reflect("Question?", "Context", draft)
        self.assertEqual(res.status, "error")
        self.assertIsNone(res.decision)
        self.assertIn("empty", res.error)
        self.assertEqual(res.final_answer, draft)

    @patch.dict("os.environ", {"REFLECTION_MODEL": "custom-reflection-model", "REFLECTION_BASE_URL": "http://test"})
    def test_reflect_model_override_source(self):
        self.assertEqual(config.get_reflection_model(), "custom-reflection-model")
        self.assertEqual(config.get_reflection_model_source(), "REFLECTION_MODEL")

    @patch.dict("os.environ", {"REFLECTION_MODEL": "", "LLM_MODEL": "default-gen-model"})
    def test_reflect_model_fallback_source(self):
        self.assertEqual(config.get_reflection_model(), "default-gen-model")
        self.assertEqual(config.get_reflection_model_source(), "LLM_MODEL fallback")


class TestRevisionExecution(unittest.TestCase):
    @patch("qa_service.revision.llm_client.generate_revision")
    def test_revise_success(self, mock_generate):
        mock_generate.return_value = "Revised grounded answer."

        refl_res = ReflectionResult(
            enabled=True,
            status="success",
            decision="REVISE",
            raw_output="Decision: REVISE\nReasons:\n- Fix X",
        )
        res = revision.revise("Question?", "Context", "Draft answer", refl_res)
        self.assertTrue(res.executed)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.revised_answer, "Revised grounded answer.")
        self.assertIsNone(res.error)

    @patch("qa_service.revision.llm_client.generate_revision")
    def test_revise_handles_exception_gracefully(self, mock_generate):
        mock_generate.side_effect = RuntimeError("Revision endpoint error")

        refl_res = ReflectionResult(
            enabled=True,
            status="success",
            decision="REVISE",
            raw_output="Decision: REVISE",
        )
        res = revision.revise("Question?", "Context", "Draft answer", refl_res)
        self.assertTrue(res.executed)
        self.assertEqual(res.status, "error")
        self.assertEqual(res.revised_answer, "")
        self.assertIn("RuntimeError", res.error)


class TestPipelineClosedLoopIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_chunk = RetrievedChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            title="Title",
            heading=None,
            source_path="doc.md",
            text="Document content",
            distance=0.1,
            rank=1,
        )

    # Test 1 — Reflection disabled (REFLECTION_ENABLED=false)
    @patch("qa_service.pipeline.retrieval.retrieve")
    @patch("qa_service.pipeline.retrieval.is_confident")
    @patch("qa_service.pipeline.llm_client.generate")
    @patch("qa_service.pipeline.reflection.reflect")
    @patch("qa_service.pipeline.config.is_reflection_enabled", return_value=False)
    def test_case1_reflection_disabled(
        self, mock_is_enabled, mock_reflect, mock_generate, mock_is_confident, mock_retrieve
    ):
        mock_retrieve.return_value = [self.mock_chunk]
        mock_is_confident.return_value = True
        mock_generate.return_value = "Draft generated answer."

        result = pipeline.answer_question("Question?")
        self.assertEqual(result.answer, "Draft generated answer.")
        mock_reflect.assert_not_called()

        steps = {s["name"]: s for s in result.trace["steps"]}
        self.assertIn("reflection", steps)
        self.assertIn("revision", steps)
        self.assertIn("final_output", steps)

        self.assertEqual(steps["reflection"]["status"], "skipped")
        self.assertEqual(steps["reflection"]["detail"]["enabled"], False)

        self.assertEqual(steps["revision"]["status"], "skipped")
        self.assertEqual(steps["revision"]["detail"]["executed"], False)

        self.assertEqual(steps["final_output"]["detail"]["source"], "generation")
        self.assertEqual(steps["final_output"]["detail"]["status"], "success")
        self.assertEqual(steps["final_output"]["detail"]["answer"], "Draft generated answer.")

    # Test 2 — Reflection PASS
    @patch("qa_service.pipeline.retrieval.retrieve")
    @patch("qa_service.pipeline.retrieval.is_confident")
    @patch("qa_service.pipeline.llm_client.generate")
    @patch("qa_service.pipeline.reflection.reflect")
    @patch("qa_service.pipeline.revision.revise")
    def test_case2_reflection_pass(
        self, mock_revise, mock_reflect, mock_generate, mock_is_confident, mock_retrieve
    ):
        mock_retrieve.return_value = [self.mock_chunk]
        mock_is_confident.return_value = True
        mock_generate.return_value = "Draft generated answer."

        mock_reflect.return_value = ReflectionResult(
            enabled=True,
            status="success",
            passed=True,
            decision="PASS",
            raw_output="Decision: PASS\nReasons:\n- Grounded",
            parsed_result=ParsedReflection(decision="PASS", reasons=["Grounded"]),
            prompt="Prompt",
            model="qwen-model",
            model_source="LLM_MODEL fallback",
            duration_ms=50.0,
        )

        result = pipeline.answer_question("Question?")
        self.assertEqual(result.answer, "Draft generated answer.")
        self.assertTrue(result.passed_reflection)
        mock_revise.assert_not_called()

        steps = {s["name"]: s for s in result.trace["steps"]}
        self.assertEqual(steps["reflection"]["status"], "ok")
        self.assertEqual(steps["reflection"]["detail"]["decision"], "PASS")
        self.assertEqual(steps["reflection"]["detail"]["model_source"], "LLM_MODEL fallback")

        self.assertEqual(steps["revision"]["status"], "skipped")
        self.assertEqual(steps["revision"]["detail"]["executed"], False)

        self.assertEqual(steps["final_output"]["detail"]["source"], "generation")
        self.assertEqual(steps["final_output"]["detail"]["answer"], "Draft generated answer.")

    # Test 3 — Reflection REVISE
    @patch("qa_service.pipeline.retrieval.retrieve")
    @patch("qa_service.pipeline.retrieval.is_confident")
    @patch("qa_service.pipeline.llm_client.generate")
    @patch("qa_service.pipeline.reflection.reflect")
    @patch("qa_service.pipeline.revision.revise")
    def test_case3_reflection_revise(
        self, mock_revise, mock_reflect, mock_generate, mock_is_confident, mock_retrieve
    ):
        mock_retrieve.return_value = [self.mock_chunk]
        mock_is_confident.return_value = True
        mock_generate.return_value = "Draft generated answer."

        mock_reflect.return_value = ReflectionResult(
            enabled=True,
            status="success",
            passed=False,
            decision="REVISE",
            raw_output="Decision: REVISE\nMissing important information:\n- Step 4",
            parsed_result=ParsedReflection(decision="REVISE", missing_information=["Step 4"]),
            prompt="Reflection Prompt",
            model="reflection-model",
            model_source="REFLECTION_MODEL",
            duration_ms=60.0,
        )

        mock_revise.return_value = RevisionResult(
            executed=True,
            status="success",
            revised_answer="Revised complete answer with Step 4.",
            prompt="Revision Prompt",
            input={"question": "Question?", "draft_answer": "Draft generated answer."},
            output="Revised complete answer with Step 4.",
            duration_ms=120.0,
            model="generation-model",
        )

        result = pipeline.answer_question("Question?")
        self.assertEqual(result.answer, "Revised complete answer with Step 4.")
        self.assertFalse(result.passed_reflection)

        steps = {s["name"]: s for s in result.trace["steps"]}
        self.assertEqual(steps["reflection"]["status"], "ok")
        self.assertEqual(steps["reflection"]["detail"]["decision"], "REVISE")
        self.assertEqual(steps["reflection"]["detail"]["missing_information"], ["Step 4"])

        self.assertEqual(steps["revision"]["status"], "ok")
        self.assertEqual(steps["revision"]["detail"]["executed"], True)
        self.assertEqual(steps["revision"]["detail"]["output"], "Revised complete answer with Step 4.")

        final_out = steps["final_output"]["detail"]
        self.assertEqual(final_out["source"], "revision")
        self.assertEqual(final_out["status"], "success")
        self.assertEqual(final_out["answer"], "Revised complete answer with Step 4.")
        # Preserves both intermediate answers in trace
        self.assertEqual(final_out["draft_answer"], "Draft generated answer.")
        self.assertEqual(final_out["revised_answer"], "Revised complete answer with Step 4.")

    # Test 4 — Reflection error
    @patch("qa_service.pipeline.retrieval.retrieve")
    @patch("qa_service.pipeline.retrieval.is_confident")
    @patch("qa_service.pipeline.llm_client.generate")
    @patch("qa_service.pipeline.reflection.reflect")
    @patch("qa_service.pipeline.revision.revise")
    def test_case4_reflection_error(
        self, mock_revise, mock_reflect, mock_generate, mock_is_confident, mock_retrieve
    ):
        mock_retrieve.return_value = [self.mock_chunk]
        mock_is_confident.return_value = True
        mock_generate.return_value = "Draft generated answer."

        mock_reflect.return_value = ReflectionResult(
            enabled=True,
            status="error",
            passed=None,
            decision=None,
            raw_output="",
            error="APIConnectionError: Failed to connect to Reflection provider",
            duration_ms=10.0,
            model="qwen-model",
            model_source="LLM_MODEL fallback",
        )

        result = pipeline.answer_question("Question?")
        # Preserves draft answer
        self.assertEqual(result.answer, "Draft generated answer.")
        self.assertIsNone(result.passed_reflection)
        mock_revise.assert_not_called()

        steps = {s["name"]: s for s in result.trace["steps"]}
        self.assertEqual(steps["reflection"]["status"], "error")
        self.assertEqual(steps["reflection"]["detail"]["status"], "error")
        self.assertIn("APIConnectionError", steps["reflection"]["detail"]["error"])

        self.assertEqual(steps["revision"]["status"], "skipped")
        self.assertEqual(steps["final_output"]["detail"]["source"], "generation")
        self.assertEqual(steps["final_output"]["detail"]["status"], "success")
        self.assertEqual(steps["final_output"]["detail"]["answer"], "Draft generated answer.")

    # Test 5 — Revision error
    @patch("qa_service.pipeline.retrieval.retrieve")
    @patch("qa_service.pipeline.retrieval.is_confident")
    @patch("qa_service.pipeline.llm_client.generate")
    @patch("qa_service.pipeline.reflection.reflect")
    @patch("qa_service.pipeline.revision.revise")
    def test_case5_revision_error(
        self, mock_revise, mock_reflect, mock_generate, mock_is_confident, mock_retrieve
    ):
        mock_retrieve.return_value = [self.mock_chunk]
        mock_is_confident.return_value = True
        mock_generate.return_value = "Draft generated answer."

        mock_reflect.return_value = ReflectionResult(
            enabled=True,
            status="success",
            passed=False,
            decision="REVISE",
            raw_output="Decision: REVISE",
            parsed_result=ParsedReflection(decision="REVISE"),
            duration_ms=40.0,
        )

        mock_revise.return_value = RevisionResult(
            executed=True,
            status="error",
            revised_answer="",
            error="Revision rate limit exceeded",
            duration_ms=15.0,
        )

        result = pipeline.answer_question("Question?")
        # Preserves draft answer on revision error
        self.assertEqual(result.answer, "Draft generated answer.")

        steps = {s["name"]: s for s in result.trace["steps"]}
        self.assertEqual(steps["reflection"]["detail"]["decision"], "REVISE")
        self.assertEqual(steps["revision"]["status"], "error")
        self.assertEqual(steps["revision"]["detail"]["error"], "Revision rate limit exceeded")

        self.assertEqual(steps["final_output"]["detail"]["source"], "generation")
        self.assertEqual(steps["final_output"]["detail"]["status"], "success")
        self.assertEqual(steps["final_output"]["detail"]["answer"], "Draft generated answer.")


if __name__ == "__main__":
    unittest.main()
