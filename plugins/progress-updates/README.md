# Progress Updates (Antigravity Plugin)

Bundles the `Mid-Run Progress Updates` instruction rule (`rules/AGENTS.md`) and a `PreInvocation` nudge hook (`hooks/progress-nudge.py`) into one toggleable Antigravity plugin.

## Behavior

1. **Rule (`rules/AGENTS.md`)**: Instructs the agent to surface assumptions, scope choices, pivots, and pre-change commitments in 1–2 plain sentences while keeping routine read/search loops quiet in chat (using `update_focus` for live activity instead of listing files read).
2. **Nudge hook (`hooks/progress-nudge.py`)**: Scans the session transcript before each model call. After at least `minSilentTurns` (`6`) consecutive silent work turns **and** `minSilentSeconds` (`45`) elapsed seconds since the last user prompt, visible update, or hook nudge (ignoring UI-only turns with `update_focus` / `update_steps`), injects a conditional `systemMessage` reminder.

Disabling the plugin in Antigravity Customizations turns off both the rule and the hook immediately.

## Requirements

- Python 3 (standard library only; no third-party packages).
- `hooks.json` invokes `python3 ./hooks/progress-nudge.py` (tested on macOS and Linux; Windows users may need `python hooks/progress-nudge.py`).

## Setup

### Global install via `agy` CLI

```bash
agy plugin install https://github.com/velazcod/agy-plugins/tree/main/plugins/progress-updates
```

To stay synced with a local clone without reinstalling after `git pull`, symlink the plugin folder instead:

```bash
mkdir -p ~/.gemini/config/plugins
ln -sfn "$(pwd)/plugins/progress-updates" ~/.gemini/config/plugins/progress-updates
```

### Project-scoped install

Copy `plugins/progress-updates` to `.agents/plugins/progress-updates` in any repository to share the rule and hook without global setup.

## Custom Overrides

Place a partial JSON object in `$PLUGIN_DATA/config.json` (typically `~/.gemini/antigravity/plugin_data/progress-updates/config.json`) or `~/.gemini/config/progress-updates.json` to override defaults without editing tracked files:

```json
{
  "minSilentTurns": 6,
  "minSilentSeconds": 45,
  "ignoredTools": ["update_focus", "update_steps"],
  "marker": "Mid-run progress update:",
  "nudgeMessage": "If you are acting on an unstated assumption, changed direction, or reached a finding, state it in 1 plain sentence with your next tool call so the user can steer (never list files read). If your previously stated intent still holds, update update_focus and stay silent."
}
```

## Tests

From the plugin directory:

```bash
python3 -m unittest discover -s tests -v
```
