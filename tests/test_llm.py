"""Provider routing and operator explanations. No live credentials required."""
import json
import unittest
from unittest.mock import patch

from yieldcrest.explanations import explain_calendar
from yieldcrest.llm import respond_with_fallback, openai_respond, openai_schema


class ProviderTests(unittest.TestCase):
    def test_success_does_not_call_backup(self):
        with patch("yieldcrest.llm.gemini_respond",return_value=("Gemini answer",[],"gemini-test")), patch("yieldcrest.llm.openai_respond") as backup:
            result=respond_with_fallback("question",[],{},gemini_key="test",openai_key="test")
            self.assertEqual(result["provider"],"Gemini")
            backup.assert_not_called()

    def test_failure_restarts_question_and_context_at_openai(self):
        context={"current_calendar":{"break_even_gross":13943}}
        history=[{"role":"user","content":"Earlier question"}]
        with patch("yieldcrest.llm.gemini_respond",side_effect=RuntimeError("Gemini quota is exhausted.")), patch("yieldcrest.llm.openai_respond",return_value=("Backup answer",[],"openai-test")) as backup:
            result=respond_with_fallback("move earlier",history,context,gemini_key="test",openai_key="test")
            self.assertEqual(result["provider"],"OpenAI")
            self.assertIn("quota",result["fallback_reason"])
            self.assertEqual(backup.call_args.args[1:4],("move earlier",history,context))

    def test_openai_only(self):
        with patch("yieldcrest.llm.gemini_respond") as primary, patch("yieldcrest.llm.openai_respond",return_value=("Ready",[],"test")):
            result=respond_with_fallback("question",[],{},openai_key="test")
            self.assertEqual(result["provider"],"OpenAI")
            self.assertFalse(result["fallback_reason"])
            primary.assert_not_called()

    def test_missing_backup_has_actionable_error(self):
        with patch("yieldcrest.llm.gemini_respond",side_effect=RuntimeError("Timed out")):
            with self.assertRaisesRegex(RuntimeError,"OPENAI_API_KEY"):
                respond_with_fallback("question",[],{},gemini_key="test")

    def test_both_providers_fail(self):
        with patch("yieldcrest.llm.gemini_respond",side_effect=RuntimeError("Timed out")), patch("yieldcrest.llm.openai_respond",side_effect=RuntimeError("OpenAI rejected the API key.")):
            with self.assertRaisesRegex(RuntimeError,"OpenAI rejected"):
                respond_with_fallback("question",[],{},gemini_key="test",openai_key="test")

    def test_openai_tool_protocol(self):
        results=[
            {"status":"completed","output":[{"type":"function_call","name":"compare_calendar",
              "arguments":json.dumps({"request_id":1,"face":1,"shift":-5}),"call_id":"call_1","id":"fc_1"}]},
            {"status":"completed","output":[{"type":"message","role":"assistant",
              "content":[{"type":"output_text","text":"The computed threshold is ₹10,339."}]}]},
        ]
        with patch("yieldcrest.llm.openai_call",side_effect=results) as api, patch("yieldcrest.llm.execute_tool",return_value={"break_even_gross":10339}) as tool:
            text,traces,model=openai_respond("test","move earlier",[],{})
            self.assertIn("10,339",text)
            self.assertEqual(len(traces),1)
            tool.assert_called_once()
            followup=api.call_args_list[1].args[1]
            last=followup["input"][-1]
            self.assertEqual(last["type"],"function_call_output")
            self.assertEqual(last["call_id"],"call_1")
            self.assertEqual(json.loads(last["output"])["break_even_gross"],10339)
            self.assertFalse(followup["store"])
            self.assertEqual(followup["tools"][0]["parameters"]["type"],"object")

    def test_readable_explanation(self):
        result={"request":{"gross":30000,"start_date":"2026-11-25","end_date":"2026-12-09"},
                "face":"Ameerpet","offer_net":25000,"wait":{"expected":20000,"probability_zero":.4,"p10":0,"p90":50000},
                "accept":{"expected":33000},"difference":13000,"break_even_gross":18000,
                "evidence":{"local_bookings":12,"pooled_bookings":100,"local_weight":.3}}
        paragraphs=explain_calendar(result)
        text=" ".join(paragraphs)
        self.assertIn("₹30,000",text)
        self.assertIn("₹18,000",text)
        self.assertIn("40%",text)
        self.assertNotIn('"comparison":',text)


if __name__=="__main__":
    unittest.main()
