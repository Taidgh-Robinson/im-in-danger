from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ralph_loop.work_items import WorkItem, load_work_item


class WorkItemTests(TestCase):
    def test_loads_and_renders_structured_work_item(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "work-item.toml"
            path.write_text(
                """
title = "Add export"
description = "Export records as JSON."
definition_of_done = ["Tests pass."]
acceptance_criteria = ["The output is valid JSON."]
constraints = ["Use the standard library."]
verification = ["python -m unittest"]
""",
                encoding="utf-8",
            )

            work_item = load_work_item(path)

            self.assertEqual(work_item.title, "Add export")
            prompt = work_item.as_prompt()
            self.assertIn("## Definition of done\n\n- Tests pass.", prompt)
            self.assertIn("## Acceptance criteria", prompt)
            self.assertIn("- `python -m unittest`", prompt)

    def test_rejects_missing_required_fields(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "work-item.toml"
            path.write_text('title = "Incomplete"\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "description"):
                load_work_item(path)

    def test_rejects_empty_acceptance_criteria(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "work-item.toml"
            path.write_text(
                """
title = "Incomplete"
description = "Missing outcomes."
definition_of_done = ["Tests pass."]
acceptance_criteria = []
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "acceptance_criteria"):
                load_work_item(path)

    def test_optional_sections_default_to_empty(self) -> None:
        work_item = WorkItem(
            title="Small change",
            description="Make the change.",
            definition_of_done=("Tests pass.",),
            acceptance_criteria=("Behavior is observable.",),
        )

        prompt = work_item.as_prompt()

        self.assertNotIn("## Constraints", prompt)
        self.assertNotIn("## Verification", prompt)

    def test_optional_sections_may_be_empty_arrays(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "work-item.toml"
            path.write_text(
                """
title = "Small change"
description = "Make the change."
definition_of_done = ["Tests pass."]
acceptance_criteria = ["Behavior is observable."]
constraints = []
verification = []
""",
                encoding="utf-8",
            )

            work_item = load_work_item(path)

            self.assertEqual(work_item.constraints, ())
            self.assertEqual(work_item.verification, ())
