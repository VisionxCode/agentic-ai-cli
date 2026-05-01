import types
import unittest
from unittest.mock import patch

from app.asyncio_compat import configure_windows_event_loop_policy


class AsyncioCompatTests(unittest.TestCase):
    def test_configure_windows_event_loop_policy_uses_proactor_policy_when_available(self):
        fake_asyncio = types.SimpleNamespace(
            WindowsProactorEventLoopPolicy=lambda: "proactor-policy",
            set_event_loop_policy=lambda policy: setattr(fake_asyncio, "policy", policy),
        )

        with patch("app.asyncio_compat.os.name", "nt"), patch(
            "app.asyncio_compat.asyncio", fake_asyncio
        ):
            configure_windows_event_loop_policy()

        self.assertEqual("proactor-policy", fake_asyncio.policy)


if __name__ == "__main__":
    unittest.main()
