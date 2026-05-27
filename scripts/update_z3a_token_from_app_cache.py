#!/usr/bin/env python3
"""Update Z3A tokens in .env.dev from the QiYun app local cache.

This script intentionally never prints token values. It reports token length and
JWT expiry only, then updates Z3A_TOKEN and Z3A_REFRESH_TOKEN when --apply is
provided.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


APP_CACHE_RELATIVE = Path("iot7.cn") / "七云物联" / "shared_preferences.json"
ACCESS_CACHE_KEY = "flutter.token"
REFRESH_CACHE_KEY = "flutter.token2"
ENV_ACCESS_KEY = "Z3A_TOKEN"
ENV_REFRESH_KEY = "Z3A_REFRESH_TOKEN"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_cache_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set; pass --cache-file explicitly.")
    return Path(appdata) / APP_CACHE_RELATIVE


def decode_jwt_exp(token: str) -> datetime | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return None
    exp = data.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    return datetime.fromtimestamp(exp, tz=timezone.utc)


def format_exp(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    local = dt.astimezone()
    return f"{local:%Y-%m-%d %H:%M:%S %Z} ({dt:%Y-%m-%d %H:%M:%S UTC})"


def read_app_tokens(cache_file: Path) -> tuple[str, str]:
    try:
        raw = cache_file.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise RuntimeError(f"App cache file not found: {cache_file}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"App cache file is not valid JSON: {cache_file}") from exc

    access = str(data.get(ACCESS_CACHE_KEY, "") or "").strip()
    refresh = str(data.get(REFRESH_CACHE_KEY, "") or "").strip()
    if not access:
        raise RuntimeError(f"Missing {ACCESS_CACHE_KEY} in {cache_file}")
    if not refresh:
        raise RuntimeError(f"Missing {REFRESH_CACHE_KEY} in {cache_file}")
    return access, refresh


def read_env_lines(env_file: Path) -> tuple[str, list[str]]:
    if not env_file.exists():
        raise RuntimeError(f"Env file not found: {env_file}")
    text = env_file.read_text(encoding="utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    return newline, text.splitlines()


def env_value(lines: list[str], key: str) -> str | None:
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def update_env_lines(lines: list[str], values: dict[str, str]) -> tuple[list[str], bool]:
    updated = []
    seen = set()
    changed = False

    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            updated.append(line)
            continue
        key = line.split("=", 1)[0]
        if key in values:
            new_line = f"{key}={values[key]}"
            updated.append(new_line)
            seen.add(key)
            changed = changed or (line != new_line)
        else:
            updated.append(line)

    missing = [key for key in values if key not in seen]
    if missing:
        if updated and updated[-1] != "":
            updated.append("")
        for key in missing:
            updated.append(f"{key}={values[key]}")
        changed = True

    return updated, changed


def backup_file(path: Path, backup_dir: Path | None = None) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = backup_dir or path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    backup = target_dir / f"{path.name}.bak.{ts}"
    shutil.copy2(path, backup)
    return backup


def write_env_file(env_file: Path, lines: list[str], newline: str) -> None:
    content = newline.join(lines) + newline
    env_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        delete=False,
        dir=str(env_file.parent),
        prefix=f".{env_file.name}.",
        suffix=".tmp",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(env_file)


def run_command(command: list[str], cwd: Path) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=str(cwd), check=True)


def check_backend_status(url: str, attempts: int, delay_seconds: float) -> None:
    last_error: Exception | None = None
    body = ""
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(url, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
            break
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                raise RuntimeError(
                    f"Backend status check failed after {attempts} attempts: {exc}"
                ) from exc
            print(
                f"Backend not ready yet ({attempt}/{attempts}): {exc}; "
                f"retrying in {delay_seconds:g}s..."
            )
            time.sleep(delay_seconds)

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"Status response is not JSON: {body[:200]}")
        return
    safe_keys = [
        "token_set",
        "token_valid",
        "token_expires",
        "phone_configured",
        "password_configured",
        "base_url",
    ]
    safe_data = {key: data.get(key) for key in safe_keys if key in data}
    print("Backend Z3A status:")
    print(json.dumps(safe_data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    root = repo_root()
    parser = argparse.ArgumentParser(
        description="Extract Z3A tokens from QiYun app cache and update .env.dev."
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=None,
        help="Path to shared_preferences.json. Defaults to %%APPDATA%%\\iot7.cn\\七云物联\\shared_preferences.json.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=root / ".env.dev",
        help="Env file to update. Defaults to repo .env.dev.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Directory for env backups. Defaults to env file directory.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write .env.dev. Without this flag the script only reports what would change.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create an env backup before writing. Not recommended.",
    )
    parser.add_argument(
        "--recreate-backend",
        action="store_true",
        help="After updating, recreate the backend container so Docker reloads .env.dev.",
    )
    parser.add_argument(
        "--check-status",
        action="store_true",
        help="Call the backend Z3A status endpoint after optional update/recreate.",
    )
    parser.add_argument(
        "--status-url",
        default="http://localhost:8000/api/z3a/status/",
        help="Backend status URL used by --check-status.",
    )
    parser.add_argument(
        "--status-attempts",
        type=int,
        default=12,
        help="Number of retry attempts for --check-status.",
    )
    parser.add_argument(
        "--status-delay",
        type=float,
        default=5.0,
        help="Seconds between --check-status retry attempts.",
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=root / "docker-compose-dev.yml",
        help="Compose file used by --recreate-backend.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = repo_root()
    cache_file = args.cache_file or default_cache_path()
    env_file = args.env_file

    access, refresh = read_app_tokens(cache_file)
    access_exp = decode_jwt_exp(access)
    refresh_exp = decode_jwt_exp(refresh)

    print(f"Cache file: {cache_file}")
    print(f"Env file:   {env_file}")
    print(f"{ACCESS_CACHE_KEY}: length={len(access)}, exp={format_exp(access_exp)}")
    print(f"{REFRESH_CACHE_KEY}: length={len(refresh)}, exp={format_exp(refresh_exp)}")

    newline, lines = read_env_lines(env_file)
    current_access = env_value(lines, ENV_ACCESS_KEY)
    current_refresh = env_value(lines, ENV_REFRESH_KEY)
    print(f"{ENV_ACCESS_KEY}: {'will update' if current_access != access else 'already current'}")
    print(f"{ENV_REFRESH_KEY}: {'will update' if current_refresh != refresh else 'already current'}")

    new_lines, changed = update_env_lines(
        lines,
        {
            ENV_ACCESS_KEY: access,
            ENV_REFRESH_KEY: refresh,
        },
    )

    if not changed:
        print("No env changes needed.")
    elif not args.apply:
        print("Dry run only. Re-run with --apply to update .env.dev.")
    else:
        if not args.no_backup:
            backup = backup_file(env_file, args.backup_dir)
            print(f"Backup created: {backup}")
        write_env_file(env_file, new_lines, newline)
        print("Env updated.")

    if args.recreate_backend:
        if not args.apply:
            print("Skipped backend recreate because --apply was not provided.")
        else:
            run_command(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(args.compose_file),
                    "up",
                    "-d",
                    "--force-recreate",
                    "--no-deps",
                    "backend",
                ],
                cwd=root,
            )

    if args.check_status:
        check_backend_status(args.status_url, args.status_attempts, args.status_delay)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}", file=sys.stderr)
        raise SystemExit(exc.returncode)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
