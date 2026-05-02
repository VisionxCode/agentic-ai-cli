from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.reconstruction_priorities import reconstruction_priorities


def build_coder_static_prompt() -> dict[str, Any]:
    return {
        "task": "Generate or revise a multi-file source-code app matching the original image.",
        "source_path": "index.html",
        "source_root": ".",
        "workspace_boundary": (
            "The file tools are scoped to this job's source folder. Use only relative paths "
            "such as index.html, styles.css, and app.js. Do not use absolute paths."
        ),
        "reconstruction_priorities": reconstruction_priorities(),
        "skill_context": {
            "available_tools": [
                "list_skill_files(skill_name, relative_dir='.')",
                "read_skill_file(skill_name, relative_path, max_chars=30000)",
            ],
            "image_sourcecode_skill_name": "image_to_sourcecode",
            "iconography_skill_name": "iconography",
            "tailwind_skill_name": "tailwind_css",
            "tailwind_browser_script": "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4",
            "huashu_skill_name": "huashu_design",
            "huashu_main_skill": "assets/source/SKILL.md",
            "huashu_references_dir": "assets/source/references",
            "huashu_react_setup": "assets/source/references/react-setup.md",
            "huashu_assets_dir": "assets/source/assets",
            "tailwind": (
                "Use Tailwind utility classes when they speed up faithful layout, spacing, "
                "typography, or color matching. Use local CSS for precise screenshot-only "
                "details, custom shapes, or deterministic fallback styles."
            ),
            "react_components": (
                "Use React components when the source has repeated UI units, interactive state, "
                "design variants, or Huashu reusable assets. For simple static screenshots, "
                "plain semantic HTML remains acceptable."
            ),
            "icons": (
                "For icon or vector asset decisions, read the iconography skill. Prefer "
                "inline/local SVG for deterministic screenshot matching. Use Google Material "
                "Symbols as the default coherent UI icon vocabulary when font loading is "
                "acceptable, and Iconify/MCP retrieval for broader or branded icon sets when "
                "available."
            ),
            "web_search": (
                "When MiniMax MCP tools are available, use them for current product facts, "
                "official brand assets, logos, screenshots, release/spec checks, and source URLs."
            ),
        },
        "workflow": (
            "If this is the first iteration, create source_path as the entry file for the "
            "current web target and create any supporting CSS, JavaScript, or local asset files "
            "in source_root, for example styles.css, app.js, components.jsx, and icons.svg. "
            "Use relative links from index.html so Playwright can load the files from disk. "
            "When Tailwind is helpful for fast faithful layout, include the Tailwind browser "
            "script from https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4 and still keep "
            "local CSS for exact visual details or fallback styling. When React components are "
            "helpful, use the Huashu React+Babel pattern: pinned React and Babel scripts, "
            "script type=\"text/babel\" component files such as components.jsx, unique per-file "
            "style object names, and Object.assign(window, {...}) for any cross-file components. "
            "On later iterations, use list_source_files plus read_text_file/read_html_lines to "
            "inspect the existing app, then make targeted edits with replace_html_lines, "
            "insert_html_after_line, or write_text_file as appropriate. Do not recreate all "
            "files from scratch unless the existing app is unusable."
        ),
        "artifact_memory": {
            "principle": (
                "Treat saved artifacts as the source of truth. Use the working source files, "
                "previous rendered screenshot, and previous evaluator report to understand what "
                "changed and what still needs correction."
            ),
            "source_files": (
                "The full current app is on disk under source_root; inspect it with file tools "
                "instead of relying on prompt source text."
            ),
            "render_feedback": (
                "When provided, compare the previous rendered screenshot against the original "
                "reference image before editing."
            ),
            "evaluation_feedback": (
                "Use previous_evaluation as the latest critique and priority list for "
                "targeted fixes."
            ),
        },
        "required_first_revision_actions": [
            "list_source_files",
            "read_text_file or read_html_lines for files likely affected by previous_evaluation",
        ],
        "revision_rules": [
            "Use tool names exactly as listed. Never add spaces, punctuation, namespace "
            "prefixes, or aliases.",
            "For revision iterations, first call list_source_files, then read_text_file "
            "or read_html_lines before editing.",
            "Before editing, search for the affected section and read nearby numbered lines.",
            "Prefer small line-range replacements in index.html and focused "
            "CSS/JavaScript file updates.",
            "Preserve useful existing HTML/CSS/JavaScript structure.",
            "Use write_html_file only for the first HTML draft or if source_path is "
            "corrupt/unusable.",
            "Use write_text_file to create or update supporting .css and .js files in source_root.",
            "After edits are saved, return UPDATED_SOURCE_READY instead of the whole document.",
        ],
        "output_contract": (
            "Persist the entry HTML in source_path and supporting assets in source_root. If you "
            "return complete HTML, it will be written to source_path as a fallback. Otherwise "
            "return UPDATED_SOURCE_READY."
        ),
    }


def build_coder_dynamic_context(
    *,
    iteration_number: int,
    source_exists: bool,
    source_manifest: list[dict[str, Any]],
    previous_evaluation: dict[str, Any] | None,
    user_note: str | None,
    previous_screenshot_path: Path | None,
) -> dict[str, Any]:
    image_inputs = [{"label": "original_reference", "detail": "high"}]
    if previous_screenshot_path is not None:
        image_inputs.append({"label": "previous_rendered_screenshot", "detail": "high"})

    return {
        "iteration_number": iteration_number,
        "source_exists": source_exists,
        "source_manifest": source_manifest,
        "previous_evaluation": previous_evaluation,
        "user_note": user_note,
        "image_inputs": image_inputs,
    }


def build_complete_html_fallback_prompt(
    *,
    previous_output: str,
    current_source: str | None,
    previous_evaluation: dict[str, Any] | None,
    iteration_number: int,
    user_note: str | None,
) -> dict[str, Any]:
    return {
        "task": "Return a complete standalone HTML document matching the original image.",
        "reason": (
            "The previous attempt did not create index.html and did not return complete HTML. "
            "Do not call tools in this fallback. Return only the full HTML document."
        ),
        "source_path": "index.html",
        "iteration_number": iteration_number,
        "previous_output_preview": previous_output[:1000],
        "current_source_preview": (current_source or "")[:12000],
        "previous_evaluation": previous_evaluation,
        "user_note": user_note,
        "requirements": [
            "Start with <!doctype html> or <html>.",
            "Include CSS and JavaScript inline unless external files are absolutely necessary.",
            "If current_source_preview is present, revise it according to "
            "previous_evaluation instead of starting from an unrelated layout.",
            "Do not return markdown, code fences, JSON, explanations, or UPDATED_SOURCE_READY.",
            "The returned document will be written directly to index.html.",
        ],
    }
