# Iconography

Use icons as source-code assets, not as decoration filler. Add an icon only when it communicates a visible control, object, status, brand mark, or screenshot detail.

## Default Choice

Prefer inline SVG or local SVG files for screenshot/source-code reconstruction. SVG is deterministic, works without network access, avoids font loading flashes, and can be styled with `currentColor`.

Use explicit `width`, `height`, and `viewBox`. Use `fill="none"` plus `stroke="currentColor"` for line icons, or `fill="currentColor"` for solid icons. Keep icon stroke weights visually consistent within one screen.

## Provider Guidance

Use Google Material Symbols when the design clearly uses Material-style interface icons or needs many common UI icons from one coherent vocabulary. If loading from Google Fonts is acceptable for the job, subset the request with `icon_names` and include `display=block`. Otherwise self-host the font or convert the needed symbols to SVG/local assets.

Use Iconify or an Iconify-backed MCP when the design needs a broader icon set, a specific brand/icon family, or search/retrieval across many open-source collections. Retrieved icons should be saved or inlined into the source tree when deterministic rendering matters.

Do not mix multiple icon families unless the reference image clearly does. If Material Symbols and Iconify are both available, use Material Symbols as the default UI vocabulary and Iconify for missing, branded, or non-Material icons.

## Corporate Logos

Do not recreate corporate logos from memory or approximate them with hand-drawn SVG. For brands such as Google, OpenAI, Microsoft, Apple, IBM, Meta, AWS, or any user-named company, use verified official assets when the real mark is required.

When MiniMax MCP web/search tools are available, use them before choosing a corporate logo asset. Search for the company's official brand resource center, press kit, partner marketing guidelines, developer branding page, or trademark/logo usage page. Prefer official company domains over icon aggregators, wikis, screenshots, social avatars, or search-result image previews.

Before using a corporate logo, establish and preserve:

- official source URL
- usage guideline URL when separate from the asset
- asset file path under `assets/logos/`
- whether the mark is used as content, a partner/customer logo, a sign-in/provider logo, or decorative background detail

Save approved logo assets locally under `assets/logos/` and reference them with `<img>` or framework-native image/source imports. Do not inline-edit, recolor, stretch, crop, add effects, or combine them with other marks unless the official brand guidelines allow it.

If official assets are unavailable, usage rights are unclear, or the design would imply endorsement/partnership, use the company name as plain text or a neutral generic company icon instead.

## Accessibility

For decorative icons, set `aria-hidden="true"` and keep the accessible name on the surrounding text/control. For icon-only buttons or meaningful status icons, provide an `aria-label` or visually available label.

## Quality Rules

- Match the reference icon style before matching the semantic idea.
- Keep icon boxes stable with fixed dimensions so hover states or font loading cannot shift layout.
- Do not invent logos from memory; use supplied or verified brand assets.
- Avoid repeated generic icons next to every label. Huashu-style visual work should use icons only where they carry real information or are present in the reference.
