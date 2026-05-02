from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path
from typing import Sequence

from app.config_loader import load_env_file
from app.orchestrator import JobResult
from app.providers.codex_auth import (
    CodexAuthError,
    codex_status,
    import_codex_cli_tokens,
    login_codex_device_code,
)
from app.providers.openrouter import openrouter_api_key
from app.providers.selection import resolve_provider
from app.providers.settings import (
    provider_models,
    save_active_provider,
    save_openrouter_api_key,
    save_provider_models,
    user_config_path,
)
from app.runtime import log_path_for, run_job_from_image_path


def _display_path(path: Path) -> str:
    return path.as_posix()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.main",
        description="Run the image-to-source-code agent workflow for one image.",
    )
    parser.add_argument("--image", required=True, help="Path to the original image.")
    parser.add_argument("--note", default=None, help="Optional guidance for the coder and evaluator.")
    parser.add_argument("--job-id", default=None, help="Optional job id for deterministic artifact paths.")
    parser.add_argument(
        "--provider",
        choices=["openrouter", "codex"],
        default=None,
        help="Temporarily use this provider for this run without changing saved settings.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output.")
    return parser


def build_provider_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.main provider",
        description="Select or inspect the AI provider used by the workflow.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    select = subparsers.add_parser("select", help="Choose OpenRouter or Codex and save the choice.")
    select.add_argument("--provider", choices=["openrouter", "codex"], default=None)
    select.add_argument("--model", default=None, help="Shared model for coder and evaluator.")
    select.add_argument("--coder-model", default=None)
    select.add_argument("--evaluator-model", default=None)
    select.add_argument("--openrouter-api-key", default=None)
    select.add_argument(
        "--codex-auth",
        choices=["login", "import", "status", "skip"],
        default=None,
        help="Codex auth action to run when selecting Codex.",
    )

    subparsers.add_parser("status", help="Show the saved provider and auth status.")
    return parser


def build_auth_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.main auth",
        description="Manage provider authentication.",
    )
    subparsers = parser.add_subparsers(dest="provider", required=True)
    codex = subparsers.add_parser("codex", help="Manage Codex OAuth credentials.")
    codex_subparsers = codex.add_subparsers(dest="command", required=True)
    codex_subparsers.add_parser("login", help="Sign in with Codex/ChatGPT device-code OAuth.")
    codex_subparsers.add_parser("import", help="Import tokens from the Codex CLI auth file.")
    codex_subparsers.add_parser("status", help="Show Codex auth status.")
    return parser


def result_to_dict(result: JobResult) -> dict[str, object]:
    return {
        "job_id": result.job_id,
        "status": result.status,
        "final_score": result.final_score,
        "iterations": result.iterations,
        "final_source_path": _display_path(result.final_source_path),
        "final_generated_image_path": _display_path(result.final_generated_image_path),
        "final_report_path": _display_path(result.final_report_path),
        "log_path": _display_path(log_path_for(result.job_id)),
    }


def print_text_summary(result: JobResult) -> None:
    for key, value in result_to_dict(result).items():
        print(f"{key}: {value}")


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    if raw_args and raw_args[0] == "provider":
        return provider_main(raw_args[1:])
    if raw_args and raw_args[0] == "auth":
        return auth_main(raw_args[1:])

    parser = build_parser()
    try:
        args = parser.parse_args(raw_args)
    except SystemExit as exc:
        return int(exc.code)

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Image path does not exist: {image_path}", file=sys.stderr)
        return 2
    if not image_path.is_file():
        print(f"Image path is not a file: {image_path}", file=sys.stderr)
        return 2

    try:
        result = asyncio.run(
            run_job_from_image_path(
                image_path=image_path,
                user_note=args.note,
                job_id=args.job_id,
                provider_override=args.provider,
            )
        )
    except Exception as exc:
        print(f"Job failed: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(result_to_dict(result), indent=2, sort_keys=True))
    else:
        print_text_summary(result)
    return 0


def provider_main(argv: Sequence[str] | None = None) -> int:
    parser = build_provider_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    if args.command == "status":
        _print_provider_status()
        return 0

    provider = args.provider or _prompt_provider()
    if provider == "openrouter":
        return _select_openrouter(args)
    if provider == "codex":
        return _select_codex(args)
    print(f"Unknown provider: {provider}", file=sys.stderr)
    return 2


def auth_main(argv: Sequence[str] | None = None) -> int:
    parser = build_auth_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    if args.provider == "codex":
        return _run_codex_auth_action(args.command)
    print(f"Unknown auth provider: {args.provider}", file=sys.stderr)
    return 2


def _select_openrouter(args: argparse.Namespace) -> int:
    api_key = args.openrouter_api_key
    if not api_key and not openrouter_api_key():
        try:
            api_key = getpass.getpass("OpenRouter API key (leave blank to keep env-only setup): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nProvider selection cancelled.", file=sys.stderr)
            return 130
    if api_key:
        save_openrouter_api_key(api_key)

    models = _collect_models("openrouter", args)
    if models:
        save_provider_models("openrouter", models)
    path = save_active_provider("openrouter")
    print(f"Provider saved: openrouter")
    print(f"Config: {path}")
    return 0


def _select_codex(args: argparse.Namespace) -> int:
    action = args.codex_auth or _prompt_codex_auth_action()
    if action != "skip":
        exit_code = _run_codex_auth_action(action)
        if exit_code != 0 and action != "status":
            return exit_code

    models = _collect_models("codex", args)
    if not models and not provider_models("codex"):
        print(
            "Codex model is required. Set --model, --coder-model/--evaluator-model, "
            "or enter a model when prompted.",
            file=sys.stderr,
        )
        return 2
    if models:
        save_provider_models("codex", models)
    path = save_active_provider("codex")
    print("Provider saved: codex")
    print(f"Config: {path}")
    return 0


def _run_codex_auth_action(action: str) -> int:
    try:
        if action == "login":
            path = login_codex_device_code()
            print(f"Codex login saved: {path}")
            return 0
        if action == "import":
            path = import_codex_cli_tokens()
            print(f"Codex credentials imported: {path}")
            return 0
        if action == "status":
            status = codex_status()
            print(json.dumps(status, indent=2, sort_keys=True))
            return 0 if status.get("authenticated") else 1
    except (CodexAuthError, RuntimeError) as exc:
        print(f"Codex auth failed: {exc}", file=sys.stderr)
        return 1
    print(f"Unknown Codex auth action: {action}", file=sys.stderr)
    return 2


def _print_provider_status() -> None:
    try:
        provider = resolve_provider()
    except Exception as exc:
        print(f"Provider config error: {exc}", file=sys.stderr)
        return
    print(f"provider: {provider}")
    print(f"config: {user_config_path()}")
    models = provider_models(provider)
    if models:
        print(f"coder_model: {models.get('coder', '')}")
        print(f"evaluator_model: {models.get('evaluator', '')}")
    if provider == "openrouter":
        print(f"openrouter_api_key: {'configured' if openrouter_api_key() else 'missing'}")
    if provider == "codex":
        status = codex_status()
        print(f"codex_auth: {'configured' if status.get('authenticated') else 'missing'}")


def _prompt_provider() -> str:
    while True:
        value = input("Select provider [openrouter/codex] (default: openrouter): ").strip().lower()
        if not value:
            return "openrouter"
        if value in {"openrouter", "codex"}:
            return value
        print("Please enter openrouter or codex.")


def _prompt_codex_auth_action() -> str:
    while True:
        value = input("Codex auth action [import/login/status/skip] (default: status): ").strip().lower()
        if not value:
            return "status"
        if value in {"import", "login", "status", "skip"}:
            return value
        print("Please enter import, login, status, or skip.")


def _collect_models(provider: str, args: argparse.Namespace) -> dict[str, str]:
    coder_model = (args.coder_model or "").strip()
    evaluator_model = (args.evaluator_model or "").strip()
    shared_model = (args.model or "").strip()
    if shared_model:
        coder_model = coder_model or shared_model
        evaluator_model = evaluator_model or shared_model
    if coder_model and evaluator_model:
        return {"coder": coder_model, "evaluator": evaluator_model}

    existing = provider_models(provider)
    if not coder_model:
        coder_model = existing.get("coder", "")
    if not evaluator_model:
        evaluator_model = existing.get("evaluator", "")
    if coder_model and evaluator_model:
        return {"coder": coder_model, "evaluator": evaluator_model}

    try:
        separate = input("Use separate coder/evaluator models? [y/N]: ").strip().lower()
        if separate in {"y", "yes"}:
            coder_model = coder_model or input("Coder model: ").strip()
            evaluator_model = evaluator_model or input("Evaluator model: ").strip()
        else:
            prompt = "Shared model"
            if provider == "openrouter":
                prompt += " (blank keeps app/config/models.yaml default)"
            shared = input(f"{prompt}: ").strip()
            if shared:
                coder_model = shared
                evaluator_model = shared
    except (EOFError, KeyboardInterrupt):
        return {}

    models = {}
    if coder_model:
        models["coder"] = coder_model
    if evaluator_model:
        models["evaluator"] = evaluator_model
    return models


if __name__ == "__main__":
    load_env_file(Path(__file__).resolve().parent.parent)
    raise SystemExit(main())
