---
name: tailwind-css
description: "Use Tailwind CSS guidance for coder-agent HTML/CSS/React work when utility classes can speed up faithful layout, spacing, typography, color matching, responsive states, or component styling. Use local CSS alongside Tailwind for pixel-exact screenshot details, custom shapes, and deterministic fallbacks."
---

# Tailwind CSS

Use Tailwind as a styling accelerator, not as a replacement for visual judgment. In this image-to-source workflow, the goal is still screenshot fidelity.

## When To Use

- Use Tailwind utility classes for layout, flex/grid, spacing, sizing, typography, color, borders, shadows, responsive states, and repeated component styling.
- Use React components with Tailwind when UI repeats, has state, has variants, or uses Huashu React assets.
- Keep plain HTML/CSS acceptable for simple static screenshots where Tailwind would add noise.

## Browser Prototype Setup

For no-build local prototypes, use Tailwind's current browser package:

```html
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
```

This browser setup is for development and reconstruction previews. For production-style apps, prefer a real build path such as Vite with `tailwindcss` and `@tailwindcss/vite`.

## Production-Style Setup

When the project has a frontend build pipeline, prefer the official Vite integration:

```bash
npm install tailwindcss @tailwindcss/vite
```

Then import Tailwind from CSS:

```css
@import "tailwindcss";
```

## Agent Rules

- Write complete class names. Do not construct Tailwind class names through string interpolation such as `bg-${color}-600`; map props to full class strings instead.
- Use arbitrary values for pixel-faithful details when useful, for example `top-[117px]`, `text-[22px]`, `bg-[#bada55]`, or `grid-cols-[1fr_500px_2fr]`.
- Use local `styles.css` for details that are clearer or safer as CSS: complex pseudo-elements, custom masks, unusual gradients, animation keyframes, and exact fallback styling.
- If generated classes are not present in source text, safelist them in CSS with Tailwind `@source inline()` when using a build setup.
- Do not add a Tailwind MCP server just for utilities. Official docs and this skill are enough unless a future task needs live Tailwind UI account access or a project-specific component catalog.

## Sources

- Tailwind browser setup: https://tailwindcss.com/docs/installation/play-cdn
- Tailwind Vite setup: https://tailwindcss.com/docs/installation/using-vite
- Class detection and dynamic class rules: https://tailwindcss.com/docs/detecting-classes-in-source-files
- Arbitrary values and custom CSS: https://tailwindcss.com/docs/adding-custom-styles
