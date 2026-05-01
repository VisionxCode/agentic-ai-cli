import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tools.render_screenshot import PlaywrightScreenshotRenderer


class FakeBrowser:
    def __init__(self, page):
        self.page = page

    async def new_page(self, *, viewport):
        return self.page

    async def close(self):
        return None


class FakePage:
    def __init__(self):
        self.goto_url = None

    async def goto(self, url, *, wait_until):
        self.goto_url = url
        return None

    async def screenshot(self, *, path, full_page):
        Path(path).write_bytes(b"screenshot")


class FakeChromium:
    def __init__(self):
        self.launch_kwargs = None
        self.page = FakePage()

    async def launch(self, **kwargs):
        self.launch_kwargs = kwargs
        return FakeBrowser(self.page)


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

    def test_renderer_opens_existing_source_file_so_relative_assets_load(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                source_root = Path(temp_dir) / "src"
                source_root.mkdir()
                source_path = source_root / "index.html"
                source_path.write_text(
                    '<link rel="stylesheet" href="styles.css"><h1>Hello</h1>',
                    encoding="utf-8",
                )
                (source_root / "styles.css").write_text("h1 { color: red; }", encoding="utf-8")
                output_path = Path(temp_dir) / "generated_image.png"
                renderer = PlaywrightScreenshotRenderer()
                context = FakePlaywrightContext()
                fake_module = types.SimpleNamespace(async_playwright=lambda: context)

                with patch.dict(sys.modules, {"playwright.async_api": fake_module}):
                    await renderer.render(
                        source_path=source_path,
                        output_path=output_path,
                        viewport={"width": 1440, "height": 900},
                    )

                self.assertEqual(source_path.resolve().as_uri(), context.chromium.page.goto_url)
                self.assertTrue(output_path.exists())

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
