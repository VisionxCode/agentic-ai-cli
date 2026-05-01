---
name: huashu-design
description: "Use Huashu Design for coder-agent tasks that need high-fidelity HTML visual output: app or web prototypes, interactive demos, HTML slide decks, motion/animation demos, MP4/GIF export workflows, design variants, visual direction exploration, brand-aware design work, infographic/data visualization, and expert design review. Trigger on requests such as prototype, hi-fi mockup, UI mockup, clickable app prototype, HTML deck, presentation slides, animation demo, visual style, design direction, design variants, infographic, export video, export GIF, or review this design."
---

# Huashu Design

Use this skill when a user wants the coder agent to produce polished design artifacts with HTML/CSS/JS as the working medium rather than a production web app.

The upstream Huashu Design repo is vendored in `assets/source`. Its original skill instructions are in `assets/source/SKILL.md`, with supporting references in `assets/source/references`, demos in `assets/source/demos`, scripts in `assets/source/scripts`, and reusable visual/audio assets in `assets/source/assets`.

## Workflow

1. Read `assets/source/SKILL.md` with `read_skill_file("huashu_design", "assets/source/SKILL.md")` before starting substantial Huashu work.
2. Load only the relevant upstream reference files for the task:
   - `assets/source/references/workflow.md` for the default junior-designer workflow.
   - `assets/source/references/design-context.md` and `assets/source/references/design-styles.md` for visual direction selection.
   - `assets/source/references/slide-decks.md` and `assets/source/references/editable-pptx.md` for HTML decks or PPTX export.
   - `assets/source/references/animations.md`, `assets/source/references/animation-best-practices.md`, `assets/source/references/animation-pitfalls.md`, `assets/source/references/video-export.md`, and `assets/source/references/sfx-library.md` for motion/video work.
   - `assets/source/references/tweaks-system.md` for live design variants and controls.
   - `assets/source/references/critique-guide.md` for expert design review.
   - `assets/source/references/verification.md` for browser and Playwright validation.
3. Reuse upstream assets and scripts instead of retyping large helper code. Treat `assets/source` as read-only source material unless the user explicitly asks to update the vendored skill.
4. For branded or product-specific work, use MiniMax MCP web/search tools when available to verify current product facts and official assets before designing. Do not invent logos, product specs, release status, or brand colors from memory.
5. Validate final HTML visually in a browser when practical, and use Playwright-style checks for clickable prototypes or motion timing.

## Output Bias

Prefer concrete deliverables: a working HTML file, prototype, deck, exported media pipeline, or actionable review. Keep production app concerns separate; if the request is mainly implementation of an app feature, use the project's normal engineering patterns first and apply Huashu only to the visual design surface.
