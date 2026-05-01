import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tools.render_screenshot import PlaywrightScreenshotRenderer


class FakeBrowser:
    async def new_page(self, *, viewport):
        return FakePage()

    async def close(self):
        return None


class FakePage:
    async def goto(self, url, *, wait_until):
        return None

    async def screenshot(self, *, path, full_page):
        Path(path).write_bytes(b"screenshot")


class FakeChromium:
    def __init__(self):
        self.launch_kwargs = None

    async def launch(self, **kwargs):
        self.launch_kwargs = kwargs
        return FakeBrowser()


class FakePlaywrightContext:
    chromium = FakeChromium()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None


class RenderScreenshotTests(unittest.TestCase):
    def test_renderer_launches_chromium_headless(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / "generated_image.png"
                renderer = PlaywrightScreenshotRenderer()
                context = FakePlaywrightContext()
                fake_module = types.SimpleNamespace(async_playwright=lambda: context)

                with patch.dict(sys.modules, {"playwright.async_api": fake_module}):
                    await renderer._render_with_playwright(
                        html_path=Path(temp_dir) / "source.html",
                        output_path=output_path,
                        viewport={"width": 1440, "height": 900},
                    )

                self.assertEqual({"headless": True}, context.chromium.launch_kwargs)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
