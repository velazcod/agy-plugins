# Antigravity Plugins

A collection of plugins for [Google Antigravity](https://antigravity.google).

## Plugins

| Plugin | Description | Docs |
| --- | --- | --- |
| `progress-updates` | Mid-run progress update rules and `PreInvocation` nudge hook for multi-step tasks. | [README](./plugins/progress-updates/README.md) |

## Installation

### Install one plugin with `agy`

```bash
git clone https://github.com/velazcod/agy-plugins.git
agy plugin install ./agy-plugins/plugins/progress-updates
```

### Load all plugins from a local clone

Add the `plugins/` directory to `~/.gemini/config/plugins.json`:

```json
{
  "entries": [
    { "path": "~/Development/agy-plugins/plugins" }
  ]
}
```

Antigravity scans each entry one level deep, so every plugin under `plugins/` loads automatically and stays updated with `git pull`.

### Project-scoped install

Copy any folder from `plugins/` into `.agents/plugins/` inside a repository.

## Development

Validate a plugin:

```bash
agy plugin validate --strict ./plugins/progress-updates
```

Run tests:

```bash
python3 -B -m unittest discover -s plugins/progress-updates/tests -v
```

## License

[MIT](./LICENSE)
