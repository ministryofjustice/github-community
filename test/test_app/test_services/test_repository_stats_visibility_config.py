import importlib
import os
import unittest
from unittest.mock import patch

from app.projects.repository_stats.config import visibility_config


class TestArchivedDeadline(unittest.TestCase):
    def reload(self, env):
        with patch.dict(os.environ, env, clear=False):
            if "VISIBILITY_ARCHIVED_DEADLINE" not in env:
                os.environ.pop("VISIBILITY_ARCHIVED_DEADLINE", None)
            return importlib.reload(visibility_config).VISIBILITY_ARCHIVED_DEADLINE

    def tearDown(self):
        importlib.reload(visibility_config)

    def test_default(self):
        self.assertEqual(self.reload({}), "23 October 2026")
        self.assertEqual(
            self.reload({"VISIBILITY_ARCHIVED_DEADLINE": ""}), "23 October 2026"
        )

    def test_env_override(self):
        self.assertEqual(
            self.reload({"VISIBILITY_ARCHIVED_DEADLINE": "1 December 2026"}),
            "1 December 2026",
        )


if __name__ == "__main__":
    unittest.main()
