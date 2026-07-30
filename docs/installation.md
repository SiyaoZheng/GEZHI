# Installing gezhi

This project is a local Python CLI. It is normally installed from the checked-out
repository, then pointed at a project-specific `gezhi.toml`.

## Requirements

- Python 3.11 or newer.
- Git.
- Codex CLI on `PATH` when `tok.provider = "codex_goal"`,
  `tok.provider = "codex_app_server"`, or `tik.provider = "codex_file"`.
- Claude Code CLI (`claude`) on `PATH` when `tok.provider = "claude_code_goal"` or `tik.provider = "claude_code_file"`.
- The configured review command on `PATH` or as an existing project script when
  `tik.provider = "oracle"` or `tik.provider = "checklist"`.
- `PACKYAPI_API_KEY`, `PACKYCODE_CODEX_KEY`, `OPENAI_API_KEY`, or
  `~/.config/gezhi/api.env` when `tik.provider = "api"`.
- `no-mistakes`.
- An OTLP-compatible OpenTelemetry receiver when you want external trace
  storage. Without one, the default runtime writes local JSONL traces.

## Development Install

From the `gezhi` repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

For API tik:

```bash
python3 -m pip install -e '.[openai]'
```

The API tik provider defaults to `claude-fable-5` at
`https://www.packyapi.com/v1`. Put the key in the shell environment or in a
private user file:

```text
~/.config/gezhi/api.env
PACKYAPI_API_KEY=...
```

Verify the command resolves:

```bash
gezhi -h
gezhi run -h
gezhi doctor -h
gezhi cleanup -h
gezhi heartbeat install -h
```

## User Install

For a user-level install from this checkout:

```bash
python3 -m pip install --user -e .
```

Make sure the user script directory is on `PATH`. On macOS this is often:

```bash
export PATH="$HOME/Library/Python/3.11/bin:$PATH"
```

If multiple Python versions are installed, prefer the virtualenv development
install so `gezhi`, `openai`, and test dependencies all come from the same
environment.

## Install no-mistakes

`gezhi` does not implement its own review/test/lint/PR gate. It uses
`kunchenguid/no-mistakes` and drives it non-interactively.

Official installer:

```bash
curl -fsSL https://raw.githubusercontent.com/kunchenguid/no-mistakes/main/docs/install.sh | sh
```

Go install:

```bash
go install github.com/kunchenguid/no-mistakes/cmd/no-mistakes@latest
export PATH="$HOME/go/bin:$PATH"
```

Verify:

```bash
no-mistakes --version
no-mistakes axi run --help
```

The `axi run --help` output must include `--intent`, `--yes`, and `--skip`.

## Install an Observability Receiver

OpenTelemetry tracing is on by default. `gezhi` first tries to send OTLP HTTP
traces to:

```text
http://localhost:4318/v1/traces
```

When that receiver is not reachable and no OTLP endpoint was explicitly set
through the environment, `gezhi` falls back to agent-readable local JSONL at:

```text
.gezhi/observability/traces.jsonl
```

Use an existing OTLP-compatible tool when you want external trace storage. For
collector-managed local traces, use OpenTelemetry Collector Contrib with the file
exporter:

```bash
mkdir -p .gezhi/observability
cp docs/otel-collector-file.yaml .gezhi/observability/otel-collector.yaml
docker run --rm --name gezhi-otel \
  -p 4318:4318 \
  -v "$PWD/.gezhi/observability:/observability" \
  -v "$PWD/.gezhi/observability/otel-collector.yaml:/etc/otelcol-contrib/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:latest \
  --config=/etc/otelcol-contrib/config.yaml
```

Then inspect either the collector output:

```bash
python3 -m json.tool .gezhi/observability/traces.json | head -n 80
```

or the built-in fallback:

```bash
head -n 1 .gezhi/observability/traces.jsonl | python3 -m json.tool
```

Other OTLP backends also work, including Phoenix, SigNoz, HyperDX, Honeycomb,
Grafana Tempo, and any OpenTelemetry Collector pipeline. They are not required
for agent-side observability.

To point `gezhi` at another receiver, use either config:

```toml
[observability]
endpoint = "http://localhost:4318/v1/traces"
```

or standard OpenTelemetry environment variables:

```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="http://localhost:4318/v1/traces"
export OTEL_SERVICE_NAME="gezhi"
```

Environment-provided OTLP endpoints are treated as explicit operator intent and
are not replaced by the local fallback.

Disable tracing only for isolated tests or diagnostics:

```bash
export OTEL_TRACES_EXPORTER=none
```

## Create a Goal Config

Create a starter config:

```bash
gezhi init
```

If a coding agent is doing setup for a non-expert user, start from the root
[`llms.txt`](../llms.txt) prompt or the
[`gezhi-project-setup`](../skills/gezhi-project-setup/SKILL.md) skill.
That setup path includes producer synthesis, `gezhi.toml` generation, and safe
validation checks before the first real heartbeat.

Then edit `gezhi.toml` so:

- `[artifact].path` is the one canonical product.
- `[producer].command` rebuilds that artifact from sources.
- `[tik]` uses one or more providers: deterministic `oracle`, command-backed
  `checklist`, API-backed file-upload review, Codex local-file review, or
  Claude Code local-file review.
- `[tok].write_dirs` contains the source directories that count as valid tok edits.
- `[tok].run_cwd`, when set, is where the tok process starts commands.
- `[tok].runtime_write_dirs` contains generated directories that commands may
  refresh without making them source-edit scopes.
- `[no_mistakes].intent`, when set, describes the non-interactive checkpoint intent.
- `[safety].generated_dirs` lists generated outputs the tok must not edit.

For a PDF-first research project, start from:

```bash
cp /path/to/GEZHI/examples/scientificity/gezhi.toml ./gezhi.toml
```

For the same project with both tik and tok run by Claude Code instead of Codex:

```bash
cp /path/to/GEZHI/examples/scientificity-claude/gezhi.toml ./gezhi.toml
```

Both examples invoke the `/apsr-review` slash skill on the first prompt line;
the skill must be installed in the reviewing CLI (Codex skill config for
`codex_file`, `~/.claude/skills/apsr-review/` for `claude_code_file`). For
`provider = "api"`, do not use a slash prompt; set `skill = "apsr-review"` in
`[tik]` so gezhi can inline the local `SKILL.md` before the API call.

Then adjust artifact paths, write dirs, tik provider settings, and the producer
command for that repository.

## no-mistakes Checkpoint

The no-mistakes integration has no interactive mode. It is enabled by default;
every non-dry-run heartbeat starts from a checkpointed clean Git worktree, and
successful source-change or completion transitions are checkpointed before the
runtime continues.

```toml
[no_mistakes]
binary = "no-mistakes"
mode = "lightspeed"
intent = "Rebuild, review, update source, and keep the Git worktree clean."
skip_steps = []
timeout_seconds = 0
```

When enabled, gezhi always:

1. stays on the current branch and treats it as the single-person mainline;
2. ignores `.gezhi/` runtime files through `.git/info/exclude`;
3. commits dirty project files as a checkpoint;
4. on non-default branches, runs `no-mistakes init`;
5. on non-default branches, runs
   `no-mistakes axi run --intent ... --yes [--skip ...]`.

On default branches such as `main` or `master`, gezhi records
`no_mistakes_default_branch_skipped` after checkpointing. This preserves the
single-person mainline workflow because no-mistakes itself refuses to validate
default branches and tells users to create a feature branch.

`mode = "lightspeed"` is the default. It still uses no-mistakes, but passes
`--skip review,test,document,lint,push,pr,ci` so routine heartbeats do not pay
the full review/test/docs/lint/PR/CI latency. Use `mode = "full"` for the full
pipeline, or `mode = "fast"` to keep local quality steps but skip push/PR/CI.

If Git setup, no-mistakes availability, or a non-default-branch check fails,
gezhi records the failure in state/history and keeps the heartbeat active.
This is deliberate: no-mistakes is checkpoint evidence, not a hard runtime gate.

If the heartbeat wall-clock budget expires during no-mistakes preparation or
checkpoint work, gezhi records the no-mistakes status in state/history and
keeps the heartbeat active.

Use `enabled = false` only for isolated tests or diagnostics that intentionally
do not run inside a Git repository.

## System-Level Heartbeat

For unattended progress, install a per-user OS timer:

```bash
gezhi heartbeat install --max-minutes 600
```

On macOS this writes a LaunchAgent under `~/Library/LaunchAgents/`. On Linux it
writes a systemd user service and timer under
`${XDG_CONFIG_HOME:-~/.config}/systemd/user/`. The generated service uses the
absolute `gezhi.toml` path, starts in the project root, and writes scheduler logs
under `.gezhi/system-heartbeat/`.

For a legacy goal, the default wake-up remains every 30 minutes. When
`[perpetual] enabled = true`, the default is every 5 minutes so the shortest
provider backoff can run on time. The persisted `next_due_at` still controls
whether a wake-up does work: healthy goals default to 6 hours, active or
blocked goals to 30 minutes, and provider failures to 5 minutes, 30 minutes,
then 2 hours capped.

Each OS tick invokes:

```bash
gezhi -c /absolute/path/to/gezhi.toml heartbeat tick --max-minutes 600
```

`heartbeat tick` cleans stale interrupted runtime state, runs one heartbeat, and
exits successfully when it finds an already-active heartbeat lock. That keeps
normal timer overlap from becoming a system-service failure. A perpetual tick
that is not due exits before producer, tik, or tok calls.

Useful management commands:

```bash
gezhi heartbeat paths
gezhi heartbeat status
gezhi heartbeat uninstall
```

To opt into perpetual mode, add a fixed substantive goal and an explicit
capability lease to `gezhi.toml`. Keep the lease limited to manuscript sources,
necessary analysis, and direct generated artifacts:

```toml
[perpetual]
enabled = true
substantive_goal = "Resolve the fixed substantive objections in the paper."

[lease]
version = "paper-v1"
allow_shell = true
allow_network = false
tools = ["Rscript"]

[[lease.rules]]
effect = "allow"
operations = ["create", "modify", "delete", "rename"]
paths = ["manuscript/**", "analysis/**"]

[[lease.rules]]
effect = "allow"
operations = ["create", "modify"]
paths = ["output/paper.pdf"]
```

The first run binds the exact goal and lease version. Attempts execute against
isolated copies; authorized deltas are journaled and committed under a
repository lock. On restart, journal recovery happens before new inspection.
Inspect `gezhi state` for `goal_binding`, `next_due_at`,
`attempt_supervisor`, `last_transaction`, and recovery history.

Use `gezhi stop` for a durable operator stop that does not mark the task
complete. `gezhi resume` preserves the same goal, lease, and attempt history
and makes work due again.

## Observability Defaults

The starter config includes:

```toml
[observability]
service_name = "gezhi"
endpoint = "http://localhost:4318/v1/traces"
timeout_seconds = 5
```

Each heartbeat emits spans for heartbeat progress, producer, artifact load,
tik, tok, and no-mistakes checkpoint. `gezhi` does not include a collector,
database, queue, dashboard, or trace storage; those are supplied by the OTLP
backend.

## Validate and Run

Static validation:

```bash
gezhi validate
```

Use a non-default config path by placing the global option before the command:

```bash
gezhi -c path/to/gezhi.toml validate
gezhi -c path/to/gezhi.toml run --max-minutes 600
```

Setup readiness:

```bash
gezhi doctor
```

With observability enabled, doctor also checks that the OpenTelemetry packages
are importable and reports the same export plan used at runtime: OTLP when the
endpoint is reachable or explicitly configured through the environment, local
JSONL fallback otherwise.

Prove the Codex tok path in a temporary workspace:

```bash
gezhi doctor --smoke-codex-goal
```

For `tok.provider = "codex_app_server"`, prove the Codex app-server tok path
instead:

```bash
gezhi doctor --smoke-codex-app-server
```

For `tok.provider = "claude_code_goal"`, prove the Claude Code tok path instead:

```bash
gezhi doctor --smoke-claude-code-goal
```

For `tik.provider = "codex_file"`, prove the local-file tik path too:

```bash
gezhi doctor --smoke-codex-goal --smoke-codex-file-tik
# or, with tok.provider = "codex_app_server":
gezhi doctor --smoke-codex-app-server --smoke-codex-file-tik
```

For `tik.provider = "claude_code_file"`:

```bash
gezhi doctor --smoke-codex-goal --smoke-claude-code-file-tik
```

For `tik.provider = "oracle"` or `tik.provider = "checklist"`, `gezhi doctor`
checks the configured command by default; no extra smoke flag is needed.

Run one heartbeat:

```bash
gezhi run --max-minutes 600
```

Inspect state:

```bash
gezhi state
```

Reset runtime state without deleting run artifacts:

```bash
gezhi reset
```

Clean up after an interrupted heartbeat:

```bash
gezhi cleanup
```

If a Ctrl-C left orphan provider processes for this project, use:

```bash
gezhi cleanup --kill-orphans
```

## Running From Source Without Installing

For one-off testing from another project:

```bash
PYTHONPATH=/path/to/GEZHI/src \
python3 -m gezhi.cli -c gezhi.toml run
```

This uses the checked-out source tree directly.
