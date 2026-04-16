import json
import unittest
from pathlib import Path


class AgentInstructionsTests(unittest.TestCase):
    def test_agent_instructions_json_exists_and_describes_daily_note_profile(self):
        path = Path("agent_instructions.json")
        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["entrypoint"], "uv run python main.py")
        self.assertEqual(payload["recommended_profile"], "daily_note")
        self.assertIn("daily_note", payload["profiles"])
        self.assertIn("--profile daily_note", payload["profiles"]["daily_note"]["command_markdown"])
        self.assertIn("--output json", payload["profiles"]["daily_note"]["command_json"])


if __name__ == "__main__":
    unittest.main()
