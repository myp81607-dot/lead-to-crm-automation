"""Older review corrections must not replace a newer inquiry's contact details."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import LeadService
from test_pipeline import lead


class ReviewOrderingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict("os.environ", {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.db_path = Path(folder.name) / "review.db"
        self.s = LeadService(self.db_path)

    def test_old_review_preserves_new_contact_and_keeps_its_own_assignment(self):
        old = self.s.submit(lead("old", company="Old company", service="unsure", message="Inquiry from Old company"))["event"]
        self.assertEqual(old["status"], "needs_review")
        newer = self.s.submit(lead("new", company="New company", message="Inquiry from New company"))["event"]
        self.assertEqual(newer["status"], "completed")  # Review does not block new valid inquiries.
        corrected = self.s.review("old", {"service": "automation"})
        contact = self.s.dashboard()["contacts"][0]
        self.assertEqual(contact["company"], "New company")
        self.assertEqual(contact["last_event_id"], "new")
        self.assertIn("Inquiry from New company", contact["description"])
        self.assertEqual(corrected["status"], "archived")
        self.assertEqual(corrected["attempts"], 0)
        self.assertEqual(corrected["superseded_by"], "new")
        self.assertEqual(corrected["owner"], "Workflow team / EMEA")
        self.assertIn("Contact unchanged", corrected["draft"])

    def test_corrected_email_matches_newer_existing_contact(self):
        self.s.submit(lead("old", email="incorrect-address", company="Old company"))
        self.s.submit(lead("new", email="correct@example.com", company="New company"))
        corrected = self.s.review("old", {"email": "correct@example.com"})
        self.assertEqual(corrected["status"], "archived")
        self.assertEqual(self.s.dashboard()["contacts"][0]["last_event_id"], "new")
        self.assertEqual(len(self.s.dashboard()["contacts"]), 1)

    def test_normal_review_can_create_a_contact_without_a_newer_inquiry(self):
        self.s.submit(lead("old", service="unsure"))
        self.assertEqual(self.s.review("old", {"service": "analytics"})["status"], "completed")
        self.assertEqual(self.s.dashboard()["contacts"][0]["last_event_id"], "old")

    def test_review_can_correct_to_a_different_email(self):
        self.s.submit(lead("old", service="unsure"))
        self.s.submit(lead("new", company="New company"))
        corrected = self.s.review("old", {"email": "another@example.com", "service": "support"})
        self.assertEqual(corrected["status"], "completed")
        self.assertEqual(len(self.s.dashboard()["contacts"]), 2)

    def test_later_uncertain_write_is_not_overwritten_by_review(self):
        self.s.submit(lead("old", service="unsure", company="Old company"))
        newer = self.s.submit(lead("new", company="New company", demo_outcome="timeout_after_write"))["event"]
        self.assertEqual(newer["status"], "reconcile_required")
        corrected = self.s.review("old", {"service": "automation"})
        self.assertEqual(corrected["status"], "archived")
        self.assertIsNone(corrected["contact_id"])
        self.assertIn("unconfirmed CRM attempt", corrected["reason"])
        self.assertEqual(self.s.dashboard()["contacts"][0]["company"], "New company")
        self.assertEqual(self.s.reconcile("new")["status"], "completed")

    def test_saved_review_recovers_to_filed_after_restart(self):
        self.s.submit(lead("old", service="unsure"))
        self.s.submit(lead("new", company="New company"))
        with patch.object(self.s, "process", side_effect=lambda event: event):
            self.s.review("old", {"service": "automation"})
        restarted = LeadService(self.db_path)
        restarted.process_due()
        self.assertEqual(restarted.get("old")["status"], "archived")
        self.assertEqual(restarted.dashboard()["contacts"][0]["last_event_id"], "new")


if __name__ == "__main__":
    unittest.main()
