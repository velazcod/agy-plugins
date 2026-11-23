#!/usr/bin/env python3
"""PreInvocation hook: nudge the model to surface intent or findings after long silent tool loops."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path
from typing import Any

HOOK_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = Path(os.environ.get("PLUGIN_ROOT") or HOOK_DIR.parent).resolve()

DEFAULT_CONFIG: dict[str, Any] = {
    "minSilentTurns": 6,
    "minSilentSeconds": 45,
    "ignoredTools": ["update_focus", "update_steps"],
    "marker": "Mid-run progress update:",
    "nudgeMessage": (
        "If you are acting on an unstated assumption, changed direction, or "
        "reached a finding, state it in 1 plain sentence with your next tool "
        "call so the user can steer (never list files read). If your "
        "previously stated intent still holds, update update_focus and stay silent."
    ),
}


def _apply_override(config: dict[str, Any], override: dict[str, Any]) -> None:
    config.update(override)
    if "maxSilentTurns" in override and "minSilentTurns" not in override:
        config["minSilentTurns"] = override["maxSilentTurns"]


def load_config(
    plugin_root: Path = PLUGIN_ROOT,
    plugin_data: str | None = None,
    user_override_path: Path | None = None,
) -> dict[str, Any]:
    """Load default plugin config.json merged with optional user override."""
    config = dict(DEFAULT_CONFIG)
    config_path = plugin_root / "config.json"
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                _apply_override(config, loaded)
        except (OSError, json.JSONDecodeError):
            pass

    override_candidates: list[Path] = []
    env_plugin_data = (
        plugin_data if plugin_data is not None else os.environ.get("PLUGIN_DATA")
    )
    if env_plugin_data:
        override_candidates.append(Path(env_plugin_data) / "config.json")
    override_candidates.append(
        user_override_path
        if user_override_path is not None
        else Path(os.path.expanduser("~/.gemini/config/progress-updates.json"))
    )

    for candidate in override_candidates:
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as handle:
                    override = json.load(handle)
                if isinstance(override, dict):
                    _apply_override(config, override)
            except (OSError, json.JSONDecodeError):
                pass
            break

    return config


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_nudge_entry(entry: dict[str, Any], marker: str, raw_line: str) -> bool:
    if not marker:
        return False
    content = entry.get("content")
    has_marker = marker in content if isinstance(content, str) else marker in raw_line
    if not has_marker:
        return False
    if entry.get("type") == "SYSTEM_MESSAGE":
        return True
    source = str(entry.get("source", ""))
    return source == "SYSTEM" or source.startswith("SYSTEM_")


def _has_work_tool_call(tool_calls: Any, ignored_tools: set[str]) -> bool:
    if not isinstance(tool_calls, list) or not tool_calls:
        return False
    for call in tool_calls:
        if not isinstance(call, dict):
            return True
        name = call.get("name")
        if not isinstance(name, str) or name not in ignored_tools:
            return True
    return False


def evaluate_payload(
    payload: dict[str, Any],
    config: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return PreInvocation hook output for the given stdin payload and config."""
    transcript_path = payload.get("transcriptPath", "")
    if not transcript_path:
        return {}

    min_silent_turns = int(config["minSilentTurns"])
    min_silent_seconds = float(config["minSilentSeconds"])
    raw_ignored = config.get("ignoredTools", [])
    ignored_tools = (
        {str(name) for name in raw_ignored if isinstance(name, str)}
        if isinstance(raw_ignored, list)
        else set()
    )
    marker = str(config["marker"]).strip()
    nudge_message = str(config["nudgeMessage"]).strip()
    nudge_text = f"{marker} {nudge_message}".strip() if marker else nudge_message

    silent_turns = 0
    last_reset_ts: datetime | None = None

    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")
                entry_ts = _parse_timestamp(entry.get("created_at"))

                if entry_type == "USER_INPUT" or _is_nudge_entry(entry, marker, line):
                    silent_turns = 0
                    last_reset_ts = entry_ts
                    continue

                if entry_type != "PLANNER_RESPONSE":
                    continue

                content = entry.get("content")
                if isinstance(content, str) and content.strip():
                    silent_turns = 0
                    last_reset_ts = entry_ts
                    continue

                if _has_work_tool_call(entry.get("tool_calls"), ignored_tools):
                    if silent_turns == 0 and last_reset_ts is None:
                        last_reset_ts = entry_ts
                    silent_turns += 1
    except OSError:
        return {}

    if silent_turns == 0 or silent_turns < min_silent_turns:
        return {}

    if min_silent_seconds > 0 and last_reset_ts is not None:
        current_time = (
            now.astimezone(timezone.utc)
            if now is not None
            else datetime.now(timezone.utc)
        )
        elapsed_seconds = (current_time - last_reset_ts).total_seconds()
        if elapsed_seconds < min_silent_seconds:
            return {}

    return {
        "injectSteps": [
            {"systemMessage": {"systemMessage": nudge_text}}
        ]
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            result = evaluate_payload(payload, load_config())
            print(json.dumps(result))
            return 0
    except Exception:
        pass

    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
