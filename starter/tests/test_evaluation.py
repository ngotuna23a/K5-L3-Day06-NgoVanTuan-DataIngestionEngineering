import copy
import unittest

from starter.src.evaluation import evaluate_query, select_strategy, summarize


class EvaluationTests(unittest.TestCase):
    def question(self):
        return {"id": "q1", "split": "dev", "question": "Example?", "expected_answer": "Example",
                "gold_source_id": "doc", "gold_page": 17, "evidence_quote": "A complete sentence.",
                "alternative_gold": []}

    def hit(self, text="A complete sentence.", page=17, document="doc"):
        return {"chunk_id": "chunk", "text": text, "document_id": document, "page": page,
                "metadata": {}, "score": 0.8}

    def test_source_page_and_full_evidence_are_all_required(self):
        for hit in [self.hit(page=18), self.hit(document="other"), self.hit("A complete")]:
            with self.subTest(hit=hit):
                self.assertFalse(evaluate_query(self.question(), [hit])["evidence_hit_at_3"])
        self.assertTrue(evaluate_query(self.question(), [self.hit()])["hit_at_1"])

    def test_unicode_and_whitespace_are_normalized(self):
        question = self.question()
        question["evidence_quote"] = "Caf\u00e9 is good."
        trace = evaluate_query(question, [self.hit("Cafe\u0301\n  is   good.")])
        self.assertTrue(trace["hit_at_1"])

    def test_alternative_source_is_accepted(self):
        question = self.question()
        question["alternative_gold"] = [{"gold_source_id": "another", "gold_page": 44,
                                         "evidence_quote": "Equivalent complete evidence."}]
        trace = evaluate_query(question, [self.hit("Equivalent complete evidence.", 44, "another")])
        self.assertTrue(trace["hit_at_1"])
        self.assertEqual(trace["hits"][0]["matched_gold_indices"], [1])

    def test_evidence_split_across_chunks_is_not_a_hit(self):
        trace = evaluate_query(self.question(), [self.hit("A complete"), self.hit("sentence.")])
        self.assertFalse(trace["evidence_hit_at_3"])
        self.assertTrue(all(hit["gold_source_page_match"] for hit in trace["hits"]))

    def test_fourth_result_is_ignored_and_second_result_only_hits_at_three(self):
        wrong = self.hit(document="wrong")
        trace = evaluate_query(self.question(), [wrong, self.hit()])
        self.assertFalse(trace["hit_at_1"])
        self.assertTrue(trace["evidence_hit_at_3"])
        self.assertFalse(evaluate_query(self.question(), [wrong] * 3 + [self.hit()])["evidence_hit_at_3"])

    def test_empty_results_and_empty_gold(self):
        self.assertFalse(evaluate_query(self.question(), [])["hit_at_1"])
        question = self.question()
        question["evidence_quote"] = " "
        with self.assertRaises(ValueError):
            evaluate_query(question, [self.hit()])

    def test_aggregation_keeps_splits_separate_and_rejects_duplicates(self):
        first = {**evaluate_query(self.question(), [self.hit()]), "strategy": "A"}
        second = {**first, "id": "q2", "hit_at_1": False, "evidence_hit_at_3": False}
        test = {**first, "split": "test"}
        result = summarize([first, second, test])
        self.assertEqual(result["A"]["dev"]["hit_at_1"], {"hits": 1, "total": 2, "value": 0.5})
        self.assertEqual(result["A"]["test"]["question_count"], 1)
        self.assertEqual(summarize([]), {})
        with self.assertRaises(ValueError):
            summarize([first, first])

    def candidates(self):
        metric = {"hits": 1, "total": 2, "value": 0.5}
        summary = {name: {"dev": {"hit_at_1": copy.deepcopy(metric),
                                 "evidence_hit_at_3": copy.deepcopy(metric)}} for name in "ABC"}
        ingestion = {"strategies": {name: {"ingest_seconds": 5.0} for name in "ABC"}}
        return summary, ingestion

    def test_selection_uses_hit3_before_hit1(self):
        summary, ingestion = self.candidates()
        summary["B"]["dev"]["evidence_hit_at_3"] = {"hits": 2, "total": 2, "value": 1.0}
        summary["A"]["dev"]["hit_at_1"] = {"hits": 2, "total": 2, "value": 1.0}
        self.assertEqual(select_strategy(summary, ingestion)["selected_strategy"], "B")

    def test_selection_tiebreaks_by_hit1_then_time_then_strategy(self):
        summary, ingestion = self.candidates()
        self.assertEqual(select_strategy(summary, ingestion)["selected_strategy"], "A")
        ingestion["strategies"]["C"]["ingest_seconds"] = 1.0
        self.assertEqual(select_strategy(summary, ingestion)["selected_strategy"], "C")
        summary["B"]["dev"]["hit_at_1"] = {"hits": 2, "total": 2, "value": 1.0}
        self.assertEqual(select_strategy(summary, ingestion)["selected_strategy"], "B")


if __name__ == "__main__":
    unittest.main()
