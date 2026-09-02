from __future__ import annotations

import unittest

from fastapi import FastAPI

from core.module_registry import ModuleRegistry


class ModuleRegistryFailureTests(unittest.TestCase):
    """A module whose manifest fails to import must not be reported as
    enabled - it was never actually registered (its router never got
    mounted), so `enabled=True` alongside `state="failed"` would tell
    callers of /health a broken module is live when it is not."""

    def test_failed_module_registration_is_reported_disabled(self) -> None:
        registry = ModuleRegistry()
        app = FastAPI()

        registry.register(app, "modules.this_module_does_not_exist")

        statuses = registry.list_statuses()
        self.assertEqual(len(statuses), 1)
        status = statuses[0]
        self.assertEqual(status["state"], "failed")
        self.assertFalse(status["enabled"])

        summary = registry.summary()
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["total"], 1)


if __name__ == "__main__":
    unittest.main()
