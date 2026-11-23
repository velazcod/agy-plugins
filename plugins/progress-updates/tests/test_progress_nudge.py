"""Unit tests for the Antigravity progress-updates plugin."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PLUGIN_ROOT / "hooks" / "progress-nudge.py"

_SPEC = importlib.util.spec_from_file_location("progress_nudge", SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
progress_nudge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(progress_nudge)

BASE_TIME = datetime(2026, 11, 23, 13, 0, 0, tzinfo=timezone.utc)


def _iso(offset_seconds: int) -> str:
    return (BASE_TIME + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_transcript(entries: list[dict]) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    with handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
    return Path(handle.name)


class ProgressNudgeTests(unittest.TestCase):
    def _default_config(self) -> dict:
        return progress_nudge.load_config(
            PLUGIN_ROOT,
            plugin_data="",
            user_override_path=Path("/nonexistent"),
        )

    def test_stays_silent_below_turn_threshold_even_when_time_elapsed(self) -> None:
        transcript = _write_transcript(
            [
                {"type": "USER_INPUT", "created_at": _iso(0), "content": "Inspect the repo"},
                {
                    "type": "PLANNER_RESPONSE",
                    "created_at": _iso(5),
                    "content": "",
                    "tool_calls": [{"name": "read_file"} for _ in range(6)],
                },
                {
                    "type": "PLANNER_RESPONSE",
                    "created_at": _iso(30),
                    "content": "",
                    "tool_calls": [{"name": "read_file"} for _ in range(6)],
                },
            ]
        )
        self.addCleanup(transcript.unlink, missing_ok=True)

        result = progress_nudge.evaluate_payload(
            {"transcriptPath": str(transcript)},
            self._default_config(),
            now=BASE_TIME + timedelta(seconds=90),
        )
        self.assertEqual(result, {})

    def test_stays_silent_below_elapsed_seconds_even_with_many_turns(self) -> None:
        entries: list[dict] = [
            {"type": "USER_INPUT", "created_at": _iso(0), "content": "Inspect files"}
        ]
        for idx in range(6):
            entries.append(
                {
                    "type": "PLANNER_RESPONSE",
                    "created_at": _iso(idx * 3),
                    "content": "",
                    "tool_calls": [{"name": "read_file"}],
                }
            )
        transcript = _write_transcript(entries)
        self.addCleanup(transcript.unlink, missing_ok=True)

        result = progress_nudge.evaluate_payload(
            {"transcriptPath": str(transcript)},
            self._default_config(),
            now=BASE_TIME + timedelta(seconds=25),
        )
        self.assertEqual(result, {})

    def test_nudges_when_both_turns_and_seconds_exceeded(self) -> None:
        entries: list[dict] = [
            {"type": "USER_INPUT", "created_at": _iso(0), "content": "Inspect files"}
        ]
        for idx in range(6):
            entries.append(
                {
                    "type": "PLANNER_RESPONSE",
                    "created_at": _iso(idx * 8),
                    "content": "",
                    "tool_calls": [{"name": "read_file"}],
                }
            )
        transcript = _write_transcript(entries)
        self.addCleanup(transcript.unlink, missing_ok=True)

        result = progress_nudge.evaluate_payload(
            {"transcriptPath": str(transcript)},
            self._default_config(),
            now=BASE_TIME + timedelta(seconds=50),
        )
        injected = result["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("Mid-run progress update:", injected)
        self.assertIn("stay silent", injected)

    def test_falls_back_to_turn_count_when_timestamps_missing(self) -> None:
        entries: list[dict] = [{"type": "USER_INPUT", "content": "Inspect files"}]
        for _ in range(6):
            entries.append(
                {
                    "type": "PLANNER_RESPONSE",
                    "content": "",
                    "tool_calls": [{"name": "read_file"}],
                }
            )
        transcript = _write_transcript(entries)
        self.addCleanup(transcript.unlink, missing_ok=True)

        result = progress_nudge.evaluate_payload(
            {"transcriptPath": str(transcript)},
            self._default_config(),
        )
        self.assertIn("injectSteps", result)

    def test_ignores_ui_only_tool_turns(self) -> None:
        entries: list[dict] = [
            {"type": "USER_INPUT", "created_at": _iso(0), "content": "Inspect files"}
        ]
        for idx in range(5):
            entries.append(
                {
                    "type": "PLANNER_RESPONSE",
                    "created_at": _iso(idx * 10),
                    "content": "",
                    "tool_calls": [{"name": "read_file"}],
                }
            )
        entries.append(
            {
                "type": "PLANNER_RESPONSE",
                "created_at": _iso(55),
                "content": "",
                "tool_calls": [{"name": "update_focus"}, {"name": "update_steps"}],
            }
        )
        transcript = _write_transcript(entries)
        self.addCleanup(transcript.unlink, missing_ok=True)

        result = progress_nudge.evaluate_payload(
            {"transcriptPath": str(transcript)},
            self._default_config(),
            now=BASE_TIME + timedelta(seconds=60),
        )
        self.assertEqual(result, {})

    def test_visible_update_and_system_sdk_marker_reset_counters_and_timer(self) -> None:
        entries: list[dict] = [
            {"type": "USER_INPUT", "created_at": _iso(0), "content": "Inspect files"},
            *[
                {
                    "type": "PLANNER_RESPONSE",
                    "created_at": _iso(idx * 10),
                    "content": "",
                    "tool_calls": [{"name": "read_file"}],
                }
                for idx in range(1, 7)
            ],
            {
                "source": "SYSTEM_SDK",
                "type": "SYSTEM_MESSAGE",
                "created_at": _iso(65),
                "content": "Mid-run progress update: If you are acting on an unstated assumption...",
            },
            {
                "type": "PLANNER_RESPONSE",
                "created_at": _iso(70),
                "content": "",
                "tool_calls": [{"name": "update_focus"}, {"name": "read_file"}],
            },
        ]
        transcript = _write_transcript(entries)
        self.addCleanup(transcript.unlink, missing_ok=True)

        result = progress_nudge.evaluate_payload(
            {"transcriptPath": str(transcript)},
            self._default_config(),
            now=BASE_TIME + timedelta(seconds=120),
        )
        self.assertEqual(result, {})

    def test_visible_update_resets_elapsed_timer(self) -> None:
        entries: list[dict] = [
            {"type": "USER_INPUT", "created_at": _iso(0), "content": "Inspect files"},
            {
                "type": "PLANNER_RESPONSE",
                "created_at": _iso(40),
                "content": "Assuming token refresh is failing; checking auth middleware next.",
                "tool_calls": [{"name": "read_file"}],
            },
            *[
                {
                    "type": "PLANNER_RESPONSE",
                    "created_at": _iso(40 + idx * 3),
                    "content": "",
                    "tool_calls": [{"name": "read_file"}],
                }
                for idx in range(1, 7)
            ],
        ]
        transcript = _write_transcript(entries)
        self.addCleanup(transcript.unlink, missing_ok=True)

        result = progress_nudge.evaluate_payload(
            {"transcriptPath": str(transcript)},
            self._default_config(),
            now=BASE_TIME + timedelta(seconds=70),
        )
        self.assertEqual(result, {})

    def test_plugin_data_override_takes_precedence_and_supports_legacy_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_data = Path(tmpdir) / "plugin_data"
            plugin_data.mkdir()
            (plugin_data / "config.json").write_text(
                json.dumps({"maxSilentTurns": 3, "nudgeMessage": "Custom nudge."}),
                encoding="utf-8",
            )
            fallback_override = Path(tmpdir) / "fallback.json"
            fallback_override.write_text(
                json.dumps({"minSilentTurns": 9}),
                encoding="utf-8",
            )

            config = progress_nudge.load_config(
                PLUGIN_ROOT,
                plugin_data=str(plugin_data),
                user_override_path=fallback_override,
            )
            self.assertEqual(config["minSilentTurns"], 3)
            self.assertEqual(config["nudgeMessage"], "Custom nudge.")
            self.assertEqual(config["minSilentSeconds"], 45)

    def test_cli_stdin_stdout_contract(self) -> None:
        old_start = (datetime.now(timezone.utc) - timedelta(seconds=90)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        entries: list[dict] = [
            {"type": "USER_INPUT", "created_at": old_start, "content": "Inspect"}
        ]
        for _ in range(6):
            entries.append(
                {
                    "type": "PLANNER_RESPONSE",
                    "created_at": old_start,
                    "content": "",
                    "tool_calls": [{"name": "read_file"}],
                }
            )
        transcript = _write_transcript(entries)
        self.addCleanup(transcript.unlink, missing_ok=True)

        env = dict(os.environ)
        env["PLUGIN_ROOT"] = str(PLUGIN_ROOT)
        env["PLUGIN_DATA"] = "/nonexistent"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            input=json.dumps({"transcriptPath": str(transcript)}),
            text=True,
            capture_output=True,
            env=env,
            check=True,
        )
        output = json.loads(proc.stdout)
        self.assertIn("injectSteps", output)


if __name__ == "__main__":
    unittest.main()
