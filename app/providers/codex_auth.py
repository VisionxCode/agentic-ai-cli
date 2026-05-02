from __future__ import annotations

import base64
import json
import os
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.providers.settings import app_home


AUTH_STORE_VERSION = 1
CODEX_PROVIDER_ID = "codex"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120
DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"


class CodexAuthError(RuntimeError):
    pass


def codex_auth_file_path() -> Path:
    configured = os.getenv("CODEX_AUTH_FILE")
    if configured:
        return Path(configured).expanduser()
    return app_home() / "auth.json"


def codex_base_url() -> str:
    return (os.getenv("CODEX_BASE_URL", "").strip().rstrip("/") or DEFAULT_CODEX_BASE_URL)


def load_auth_store() -> dict[str, Any]:
    path = codex_auth_file_path()
    if not path.exists():
        return {"version": AUTH_STORE_VERSION, "providers": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CodexAuthError(f"Could not read Codex auth store at {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CodexAuthError(f"Codex auth store at {path} must be a JSON object")
    raw.setdefault("providers", {})
    return raw


def save_auth_store(auth_store: dict[str, Any]) -> Path:
    path = codex_auth_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    auth_store["version"] = AUTH_STORE_VERSION
    auth_store["updated_at"] = _now_iso()
    payload = json.dumps(auth_store, indent=2, sort_keys=True) + "\n"
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(path)
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def codex_status() -> dict[str, Any]:
    try:
        data = read_codex_tokens(refresh_if_expiring=False)
    except CodexAuthError as exc:
        return {
            "authenticated": False,
            "auth_file": str(codex_auth_file_path()),
            "message": str(exc),
        }
    access_token = str(data["tokens"].get("access_token", "") or "")
    return {
        "authenticated": True,
        "auth_file": str(codex_auth_file_path()),
        "base_url": codex_base_url(),
        "expires_soon": codex_access_token_is_expiring(access_token, CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS),
        "last_refresh": data.get("last_refresh"),
    }


def read_codex_tokens(
    *,
    refresh_if_expiring: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    auth_store = load_auth_store()
    providers = auth_store.get("providers")
    if not isinstance(providers, dict):
        raise CodexAuthError("Codex auth store is missing a providers object.")
    state = providers.get(CODEX_PROVIDER_ID) or providers.get("openai-codex")
    if not isinstance(state, dict):
        raise CodexAuthError(
            "Codex is selected but no Codex credentials are stored. "
            "Run `python -m app.main auth codex login` or "
            "`python -m app.main auth codex import`."
        )
    tokens = state.get("tokens")
    if not isinstance(tokens, dict):
        raise CodexAuthError("Codex auth state is missing tokens. Re-run Codex login or import.")
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise CodexAuthError("Codex auth is missing access_token. Re-run Codex login or import.")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise CodexAuthError("Codex auth is missing refresh_token. Re-run Codex login or import.")

    should_refresh = force_refresh
    if refresh_if_expiring and codex_access_token_is_expiring(
        access_token,
        CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS,
    ):
        should_refresh = True
    if should_refresh:
        tokens = refresh_codex_tokens(tokens)
        state = dict(state)
        state["tokens"] = tokens
        state["last_refresh"] = _now_iso()
        providers[CODEX_PROVIDER_ID] = state
        auth_store["providers"] = providers
        save_auth_store(auth_store)
    return {"tokens": dict(tokens), "last_refresh": state.get("last_refresh")}


def save_codex_tokens(tokens: dict[str, Any], *, source: str) -> Path:
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise CodexAuthError("Codex token payload is missing access_token.")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise CodexAuthError("Codex token payload is missing refresh_token.")
    auth_store = load_auth_store()
    providers = auth_store.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        auth_store["providers"] = providers
    providers[CODEX_PROVIDER_ID] = {
        "tokens": {
            "access_token": access_token.strip(),
            "refresh_token": refresh_token.strip(),
        },
        "auth_mode": "chatgpt",
        "source": source,
        "last_refresh": _now_iso(),
    }
    return save_auth_store(auth_store)


def import_codex_cli_tokens() -> Path:
    tokens = read_codex_cli_tokens()
    if tokens is None:
        raise CodexAuthError(
            "No usable Codex CLI credentials found. Expected tokens in "
            f"{codex_cli_auth_path()}."
        )
    return save_codex_tokens(tokens, source="codex-cli-import")


def read_codex_cli_tokens() -> dict[str, str] | None:
    auth_path = codex_cli_auth_path()
    if not auth_path.is_file():
        return None
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return None
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str):
        return None
    if not access_token.strip() or not refresh_token.strip():
        return None
    return {"access_token": access_token.strip(), "refresh_token": refresh_token.strip()}


def codex_cli_auth_path() -> Path:
    codex_home = os.getenv("CODEX_HOME", "").strip()
    if not codex_home:
        codex_home = str(Path.home() / ".codex")
    return Path(codex_home).expanduser() / "auth.json"


def login_codex_device_code() -> Path:
    tokens = run_codex_device_code_login()
    return save_codex_tokens(tokens, source="device-code")


def run_codex_device_code_login() -> dict[str, str]:
    try:
        import httpx
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install httpx to use Codex OAuth login.") from exc

    issuer = "https://auth.openai.com"
    with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
        response = client.post(
            f"{issuer}/api/accounts/deviceauth/usercode",
            json={"client_id": CODEX_OAUTH_CLIENT_ID},
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 200:
            raise CodexAuthError(f"Device code request returned status {response.status_code}.")
        device_data = response.json()
        user_code = device_data.get("user_code")
        device_auth_id = device_data.get("device_auth_id")
        poll_interval = max(3, int(device_data.get("interval", 5)))
        if not isinstance(user_code, str) or not isinstance(device_auth_id, str):
            raise CodexAuthError("Device code response did not include user_code and device_auth_id.")

        print("To authenticate Codex:")
        print(f"  1. Open {issuer}/codex/device")
        print(f"  2. Enter code: {user_code}")
        print("Waiting for sign-in. Press Ctrl+C to cancel.")

        deadline = time.monotonic() + 15 * 60
        code_response: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            time.sleep(poll_interval)
            poll_response = client.post(
                f"{issuer}/api/accounts/deviceauth/token",
                json={"device_auth_id": device_auth_id, "user_code": user_code},
                headers={"Content-Type": "application/json"},
            )
            if poll_response.status_code == 200:
                code_response = poll_response.json()
                break
            if poll_response.status_code in {403, 404}:
                continue
            raise CodexAuthError(f"Device auth polling returned status {poll_response.status_code}.")
        if code_response is None:
            raise CodexAuthError("Codex login timed out after 15 minutes.")

        authorization_code = code_response.get("authorization_code")
        code_verifier = code_response.get("code_verifier")
        if not isinstance(authorization_code, str) or not isinstance(code_verifier, str):
            raise CodexAuthError("Device auth response missing authorization code or verifier.")

        token_response = client.post(
            CODEX_OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": f"{issuer}/deviceauth/callback",
                "client_id": CODEX_OAUTH_CLIENT_ID,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_response.status_code != 200:
            raise CodexAuthError(f"Token exchange returned status {token_response.status_code}.")
        token_payload = token_response.json()
        access_token = token_payload.get("access_token")
        refresh_token = token_payload.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise CodexAuthError("Token exchange did not return access_token and refresh_token.")
        return {"access_token": access_token, "refresh_token": refresh_token}


def refresh_codex_tokens(tokens: dict[str, Any]) -> dict[str, str]:
    try:
        import httpx
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install httpx to refresh Codex OAuth tokens.") from exc

    refresh_token = tokens.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise CodexAuthError("Codex auth is missing refresh_token. Re-run Codex login or import.")
    with httpx.Client(timeout=httpx.Timeout(float(os.getenv("CODEX_REFRESH_TIMEOUT_SECONDS", "20")))) as client:
        response = client.post(
            CODEX_OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token.strip(),
                "client_id": CODEX_OAUTH_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code != 200:
        message = f"Codex token refresh failed with status {response.status_code}."
        relogin = response.status_code in {401, 403}
        try:
            payload = response.json()
            error = payload.get("error")
            if isinstance(error, dict):
                detail = error.get("message")
                code = error.get("code") or error.get("type")
            else:
                detail = payload.get("error_description") or payload.get("message")
                code = error
            if isinstance(detail, str) and detail.strip():
                message = f"Codex token refresh failed: {detail.strip()}"
            if code in {"invalid_grant", "invalid_token", "invalid_request", "refresh_token_reused"}:
                relogin = True
        except Exception:
            pass
        if relogin:
            message += " Re-run `python -m app.main auth codex login`."
        raise CodexAuthError(message)

    payload = response.json()
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise CodexAuthError("Codex token refresh response was missing access_token.")
    next_refresh = payload.get("refresh_token")
    return {
        "access_token": access_token.strip(),
        "refresh_token": next_refresh.strip() if isinstance(next_refresh, str) and next_refresh.strip() else refresh_token.strip(),
    }


def codex_access_token_is_expiring(access_token: str, skew_seconds: int) -> bool:
    exp = _jwt_exp(access_token)
    if exp is None:
        return False
    return exp - time.time() <= skew_seconds


def codex_headers(access_token: str) -> dict[str, str]:
    headers = {
        "User-Agent": "codex_cli_rs/0.0.0 (IBM Hackathon Agent Workflow)",
        "originator": "codex_cli_rs",
    }
    account_id = _chatgpt_account_id(access_token)
    if account_id:
        headers["ChatGPT-Account-ID"] = account_id
    return headers


def _chatgpt_account_id(access_token: str) -> str | None:
    claims = _jwt_claims(access_token)
    auth_claims = claims.get("https://api.openai.com/auth")
    if not isinstance(auth_claims, dict):
        return None
    value = auth_claims.get("chatgpt_account_id")
    return value if isinstance(value, str) and value else None


def _jwt_exp(access_token: str) -> float | None:
    exp = _jwt_claims(access_token).get("exp")
    if isinstance(exp, (int, float)):
        return float(exp)
    return None


def _jwt_claims(access_token: str) -> dict[str, Any]:
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
