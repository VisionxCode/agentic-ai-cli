from __future__ import annotations

from pathlib import Path


class PlaywrightScreenshotRenderer:
    async def render(self, *, source_html: str, output_path: Path, viewport: dict[str, int]) -> Path:
        try:
            from playwright.async_api import async_playwright
        except ModuleNotFoundError as exc:
            raise RuntimeError("Install playwright and run 'playwright install chromium'") from exc

        html_path = output_path.with_name("source.html")
        html_path.write_text(source_html, encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
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

