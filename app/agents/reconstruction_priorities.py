from __future__ import annotations

from copy import deepcopy
from typing import Any


RECONSTRUCTION_PRIORITIES: dict[str, Any] = {
    "default_mode": "ui_first",
    "primary_ui": [
        "navigation",
        "sidebars",
        "panels",
        "cards",
        "forms",
        "buttons",
        "menus",
        "tabs",
        "labels",
        "icons",
        "spacing",
        "typography",
        "colors",
        "visual hierarchy",
        "component structure",
        "states",
    ],
    "content_surfaces": [
        "feed posts",
        "comments",
        "emails",
        "documents",
        "ads",
        "recommendations",
        "media embeds",
        "message bodies",
        "table rows",
        "avatars",
        "article previews",
    ],
    "content_surface_rule": (
        "Match content surfaces by layout, density, hierarchy, visual rhythm, and representative appearance; "
        "do not over-optimize exact authored text or embedded media unless the user note asks for exact content."
    ),
    "exact_text_policy": (
        "Preserve exact text for UI labels, navigation, controls, headings, product names, pricing, status text, "
        "and content the user explicitly asks to match exactly."
    ),
    "coder_guidance": (
        "Build the reusable product/interface UI first. Use representative placeholder content for incidental "
        "authored or external regions when exact reproduction would distract from UI fidelity."
    ),
    "evaluator_scoring_guidance": (
        "Penalize broken or unprofessional UI structure more than non-exact post, comment, message, document, "
        "or ad content. Flag incidental content only when its density, visual rhythm, major media shape, or "
        "hierarchy changes the interface impression."
    ),
    "override_policy": (
        "The user note can override this default. If the user note asks to match a content surface exactly, "
        "treat that requested content as in scope for exact reconstruction."
    ),
}


def reconstruction_priorities() -> dict[str, Any]:
    return deepcopy(RECONSTRUCTION_PRIORITIES)
