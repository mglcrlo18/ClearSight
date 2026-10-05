"""
Unit tests for ClearSight Coder v3 Engine (engine/coder_v3.py).
Validates:
1. PII masking compliant with RA 10173.
2. Taglish negation transformations (NOT_ tokenization).
3. Baseline training, margin sampling, and active learning uncertainty flagging.
4. Online partial_fit updates.
"""
import unittest
from engine.coder_v3 import TaglishPreProcessor, CoderV3Engine


class TestCoderV3(unittest.TestCase):

    def setUp(self):
        self.preprocessor = TaglishPreProcessor()
        self.engine = CoderV3Engine()
        self.categories = [
            "Quality Positive",
            "Price Negative",
            "Service Positive",
            "Logistics Negative"
        ]
        self.engine.set_codeframe(self.categories)

    def test_pii_masking(self):
        text = "Tumawag ako sa 09171234567 at nag-email sa test.user@clearsight.ph kahapon."
        cleaned = self.preprocessor.mask_pii(text)
        self.assertNotIn("09171234567", cleaned)
        self.assertNotIn("test.user@clearsight.ph", cleaned)
        self.assertIn("[PHONE_MASKED]", cleaned)
        self.assertIn("[EMAIL_MASKED]", cleaned)

    def test_negation_processing(self):
        text = "Hindi maganda ang tela, di maayos ang tahi, wala kwenta."
        processed = self.preprocessor.process_negations(text)
        self.assertIn("NOT_maganda", processed)
        self.assertIn("NOT_maayos", processed)
        self.assertIn("NOT_kwenta", processed)

    def test_baseline_and_predict_uncertainty(self):
        seed_texts = [
            "Napakaganda ng kalidad at matibay.",
            "Sobrang mahal at hindi sulit ang presyo.",
            "Mabait at maasikaso ang customer service.",
            "Delayed ang delivery, dalawang linggo bago dumating."
        ]
        seed_labels = [0, 1, 2, 3]

        self.engine.train_baseline(seed_texts, seed_labels)
        self.assertTrue(self.engine.is_fitted)

        test_samples = [
            "Ganda ng quality, sulit na sulit!",
            "Mahal sobra, lugi ka dito."
        ]
        preds = self.engine.predict_with_uncertainty(test_samples)
        self.assertEqual(len(preds), 2)
        for p in preds:
            self.assertIn("text", p)
            self.assertIn("predicted_label", p)
            self.assertIn("confidence", p)
            self.assertIn("margin", p)
            self.assertIn("needs_review", p)
            self.assertTrue(0.0 <= p["confidence"] <= 1.0)

    def test_online_learning_partial_fit(self):
        seed_texts = ["A", "B", "C", "D"]
        seed_labels = [0, 1, 2, 3]
        self.engine.train_baseline(seed_texts, seed_labels)

        # Online correction
        new_texts = ["Mabilis dumating", "Mabagal dumating"]
        new_labels = [3, 3]
        self.engine.partial_fit_online(new_texts, new_labels)
        self.assertTrue(self.engine.is_fitted)


if __name__ == "__main__":
    unittest.main()
