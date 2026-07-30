# gezhi CLI Reference

`gezhi` is an `argparse` CLI. The parser generates `-h` and `--help`
output from the same command definitions used at runtime.

## Top Level

Omitting the command defaults to `run`. Global options must appear before the
subcommand.

```text
usage: gezhi [-h] [-c CONFIG]
                {init,validate,doctor,run,stop,resume,tik,heartbeat,state,reset,cleanup,render-prompts} ...

Configure and run GEZHI artifact-centered heartbeats for coding agents.

options:
  -h, --help            show this help message and exit
  -c, --config CONFIG   Path to gezhi.toml (default: gezhi.toml)

commands:
  {init,validate,doctor,run,stop,resume,tik,heartbeat,state,reset,cleanup,render-prompts}
    init                Create a starter artifact gezhi.toml
    validate            Validate gezhi.toml, prompt placeholders, and writable
                        scopes
    doctor              Check setup readiness before a heartbeat
    run                 Run one autonomous heartbeat
    stop                Persistently stop a perpetual goal without completing it
    resume              Resume a stopped perpetual goal from durable state
    tik                 Rebuild the artifact and run tik review, but skip tok
    heartbeat           Install or run the system-level heartbeat
    state               Print state JSON or the default initial state
    reset               Remove state and stale lock while preserving run
                        artifacts
    cleanup             Clean interrupted heartbeat locks and optional orphan
                        provider processes
    render-prompts      Render tik and tok prompts without running providers

Omitting the command defaults to run. Use 'gezhi <command> -h' for
subcommand options.
```

## Run

```text
usage: gezhi run [-h] [--dry-run] [--max-minutes MAX_MINUTES]

Run exactly one heartbeat: producer rebuild, tik review, then tok only if
review fails.

options:
  -h, --help            show this help message and exit
  --dry-run             Create a run directory and render prompts without
                        running producer, tik, or tok
  --max-minutes MAX_MINUTES
                        Maximum wall-clock minutes for the heartbeat,
                        including providers and no-mistakes
```

## Doctor

```text
usage: gezhi doctor [-h] [--smoke-codex-goal]
                       [--smoke-codex-app-server]
                       [--smoke-claude-code-goal]
                       [--smoke-codex-file-tik] [--smoke-claude-code-file-tik]
                       [--skip-openai-auth]
                       [--timeout-seconds TIMEOUT_SECONDS]
                       [--smoke-timeout-seconds SMOKE_TIMEOUT_SECONDS]

Check config, commands, providers, and smoke prerequisites before a real
heartbeat.

options:
  -h, --help            show this help message and exit
  --smoke-codex-goal    Run a minimal Codex /goal source-change smoke check in
                        a temp directory
  --smoke-codex-app-server
                        Run a minimal Codex app-server stdio tok smoke check
                        in a temp directory
  --smoke-claude-code-goal
                        Run a minimal Claude Code source-change tok smoke
                        check in a temp directory
  --smoke-codex-file-tik
                        Run a minimal Codex local-file tik smoke check in a
                        temp directory
  --smoke-claude-code-file-tik
                        Run a minimal Claude Code local-file tik smoke check
                        in a temp directory
  --skip-openai-auth    Skip API key readiness check for API tik configs
  --timeout-seconds TIMEOUT_SECONDS
                        Timeout for setup probes except optional provider
                        smoke checks
  --smoke-timeout-seconds SMOKE_TIMEOUT_SECONDS
                        Timeout for optional provider smoke checks
```

Command-backed tik providers (`oracle` and `checklist`) are covered by the
default static command checks. There is no separate checklist smoke flag.

## Tik

```text
usage: gezhi tik [-h]

Run producer plus tik against the configured artifact without source changes.

options:
  -h, --help  show this help message and exit
```

## Perpetual Stop and Resume

```text
usage: gezhi stop [-h]

Persistently stop a perpetual goal without completing it.
```

```text
usage: gezhi resume [-h]

Resume a stopped perpetual goal from durable state.
```

`stop` writes the `stopped` lifecycle state and prevents later scheduler ticks
from running producer, tik, or tok. `resume` preserves the immutable goal,
lease, attempt history, and transaction evidence, then makes the next
heartbeat due. Neither command is available as a substitute for configuring
`[perpetual] enabled = true`.

## System-Level Heartbeat

The system-level heartbeat installs an OS timer. Each tick runs at most one
bounded `gezhi` heartbeat. Perpetual scheduling is durable state shared
across ticks.

```text
usage: gezhi heartbeat [-h] {install,status,uninstall,paths,tick} ...

Manage an OS-level timer that starts one hardened heartbeat tick per schedule.

options:
  -h, --help            show this help message and exit

heartbeat commands:
  {install,status,uninstall,paths,tick}
    install             Install and start the OS-level heartbeat timer
    status              Show OS-level heartbeat service status
    uninstall           Stop and remove the OS-level heartbeat service
    paths               Print OS-level heartbeat file and log paths
    tick                Run one hardened heartbeat tick for the OS scheduler
```

```text
usage: gezhi heartbeat install [-h] [--manager {auto,launchd,systemd-user}]
                                  [--label LABEL]
                                  [--every-minutes EVERY_MINUTES]
                                  [--max-minutes MAX_MINUTES] [--no-start]
                                  [--force] [--dry-run]

Install a launchd LaunchAgent on macOS or a systemd user timer on Linux.

options:
  -h, --help            show this help message and exit
  --manager {auto,launchd,systemd-user}
                        OS service manager to use
  --label LABEL         Override the generated service label
  --every-minutes EVERY_MINUTES
                        Timer interval in minutes; defaults to 5 for perpetual
                        goals and 30 otherwise
  --max-minutes MAX_MINUTES
                        Maximum wall-clock minutes for each heartbeat tick
  --no-start            Write service files but do not load or start the timer
  --force               Overwrite an existing GEZHI-managed service file
  --dry-run             Print files and commands without writing or starting
                        anything
```

```text
usage: gezhi heartbeat tick [-h] [--max-minutes MAX_MINUTES]

Clean stale heartbeat state, run exactly one heartbeat, and treat active locks
as a skipped tick.

options:
  -h, --help            show this help message and exit
  --max-minutes MAX_MINUTES
                        Maximum wall-clock minutes for this heartbeat tick
```

`gezhi heartbeat install` writes a per-user LaunchAgent on macOS and a
per-user systemd service/timer on Linux. The generated service calls
`<python executable> -m gezhi -c /absolute/path/to/gezhi.toml heartbeat tick
--max-minutes ...`,
uses the project root as its working directory, and writes service logs under
`.gezhi/system-heartbeat/`.

`heartbeat tick` first runs runtime cleanup for stale locks/interrupted phases,
then calls the same one-heartbeat runtime as `gezhi run`. If another
heartbeat is currently active, the tick exits successfully after logging a
skipped tick so the OS scheduler does not mark normal overlap as a failure.
For perpetual goals, a not-yet-due tick also exits before producer or provider
work. The default five-minute wake-up lets the 5-minute provider backoff run on
time; healthy and active cadence still comes from `next_due_at`.

## Cleanup

```text
usage: gezhi cleanup [-h] [--kill-orphans]

Remove stale heartbeat locks, mark interrupted running phases, and optionally
stop orphan provider processes for this project.

options:
  -h, --help      show this help message and exit
  --kill-orphans  Terminate orphan GEZHI/Codex processes for this project
                  when no live heartbeat lock exists
```

## Command Summary

| Command | Effect |
| --- | --- |
| `gezhi init` | Create a starter artifact `gezhi.toml`; refuses to overwrite an existing config. |
| `gezhi validate` | Load config and print a JSON summary if config policy passes. |
| `gezhi doctor` | Run static readiness probes and optional provider smoke checks. |
| `gezhi run` | Execute exactly one heartbeat. |
| `gezhi tik` | Run producer plus tik only; do not invoke tok. |
| `gezhi heartbeat install` | Install a per-user OS timer for repeated one-heartbeat ticks. |
| `gezhi heartbeat status` | Show the OS timer status and managed file paths. |
| `gezhi heartbeat uninstall` | Stop and remove the OS timer files for this project. |
| `gezhi state` | Print current state JSON or the default initial state. |
| `gezhi reset` | Remove state and lock files; preserve run artifacts. |
| `gezhi cleanup` | Clean stale/interrupted heartbeat state. |
| `gezhi render-prompts` | Render tik and tok prompts without running providers. |
