from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.asyncio_compat import configure_windows_event_loop_policy


class PlaywrightScreenshotRenderer:
    async def render(
        self,
        *,
        output_path: Path,
        viewport: dict[str, int],
        source_path: Path | None = None,
        source_html: str | None = None,
    ) -> Path:
        if source_path is None:
            if source_html is None:
                raise ValueError("Either source_path or source_html is required.")
            source_path = output_path.with_name("source.html")
            source_path.write_text(source_html, encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if os.name == "nt":
            return await asyncio.to_thread(
                self._render_in_fresh_event_loop,
                source_path,
                output_path,
                viewport,
            )

        return await self._render_with_playwright(
            html_path=source_path,
            output_path=output_path,
            viewport=viewport,
        )

    def _render_in_fresh_event_loop(
        self, html_path: Path, output_path: Path, viewport: dict[str, int]
    ) -> Path:
        configure_windows_event_loop_policy()
        return asyncio.run(
            self._render_with_playwright(
                html_path=html_path,
                output_path=output_path,
                viewport=viewport,
            )
        )

    async def _render_with_playwright(
        self, *, html_path: Path, output_path: Path, viewport: dict[str, int]
    ) -> Path:
        try:
            from playwright.async_api import async_playwright
        except ModuleNotFoundError as exc:
            raise RuntimeError("Install playwright and run 'playwright install chromium'") from exc

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={
                    "width": int(viewport.get("width", 1440)),
                    "height": int(viewport.get("height", 900)),
                }
            )
            await page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            await page.screenshot(path=str(output_path), full_page=True)
            await browser.close()
        return output_path
