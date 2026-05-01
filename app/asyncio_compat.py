from __future__ import annotations

import asyncio
import os


def configure_windows_event_loop_policy() -> None:
    if os.name != "nt":
        return

    policy_factory = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if policy_factory is not None:
        asyncio.set_event_loop_policy(policy_factory())
