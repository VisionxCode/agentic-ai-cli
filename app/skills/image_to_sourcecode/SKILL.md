# Image To Source Code

Reconstruct the screenshot as a small source-code project rooted at `src/index.html` for the current web target. Treat HTML/CSS/JavaScript as the active output format, not as the permanent limit of the workflow.

Use separate CSS files for layout, typography, color, and spacing when that keeps the work clearer. Use separate JavaScript files for behavior, generated visual details, or reusable rendering helpers. Keep the produced source modular so future targets can map the same visual decisions into framework components or other code formats.

When visual assets are needed, prefer source-level assets that render deterministically: inline SVG, local SVG files, CSS shapes, canvas only for genuinely procedural graphics, and local image assets when supplied by the job.
