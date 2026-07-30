# Migrating to GEZHI

GEZHI now has one canonical distribution, Python package, command, configuration
file, state root, and scheduler identity. This is a hard cut: the earlier
runtime interfaces are not aliases for the new ones.

## Identity Map

| Earlier interface | GEZHI interface |
| --- | --- |
| Distribution `goal-cli` | Distribution `gezhi` |
| Python package `goal_cli` | Python package `gezhi` |
| Command `goal-cli` | Command `gezhi` |
| Default config `goal.toml` | Default config `gezhi.toml` |
| Default state root `.goal/` | Default state root `.gezhi/` |
| User config `~/.config/goal-cli/` | User config `~/.config/gezhi/` |
| `GOAL_CLI_API_ENV_FILE` | `GEZHI_API_ENV_FILE` |
| `GOAL_ARTIFACT` | `GEZHI_ARTIFACT` |
| `GOAL_TIK_PROMPT` | `GEZHI_TIK_PROMPT` |
| `GOAL_RUN_DIR` | `GEZHI_RUN_DIR` |
| OTel service `goal-cli` and spans `goal_cli.*` | Service `gezhi` and spans `gezhi.*` |
| launchd label `com.goal-cli.*` | Label `io.github.siyaozheng.gezhi.*` |
| `goal-cli heartbeat uninstall` | `gezhi heartbeat uninstall` after migration |
| Skills `goal-cli-project-setup`, `goal-cli-template-author` | Skills `gezhi-project-setup`, `gezhi-template-author` |

Domain and upstream terms do not change. A project still has a goal;
`GoalConfig`, `substantive_goal`, `codex_goal`, and Codex `/goal` retain their
existing meanings.

## Migration Order

1. Stop and uninstall the earlier per-user heartbeat before installing a GEZHI
   heartbeat. If the earlier command is still available, use the original
   config and repeat the command with its custom label when applicable:

   ```bash
   goal-cli -c goal.toml heartbeat uninstall
   goal-cli -c goal.toml heartbeat uninstall --label <old-custom-label>
   ```

   If that command is unavailable, disable and remove the exact launchd or
   systemd-user files reported by GEZHI. Confirm that no earlier process or
   repository lock is active before continuing.

2. Remove the earlier Python distribution from the environment. Installing
   `gezhi` does not automatically uninstall a differently named distribution:

   ```bash
   python3 -m pip uninstall goal-cli
   ```

3. Back up, then rename the project configuration and durable state root:

   ```bash
   mv goal.toml gezhi.toml
   mv .goal .gezhi
   ```

   Edit `state_dir` and `runs_dir` inside `gezhi.toml` so they point to
   `.gezhi` and `.gezhi/runs`.

4. Move the API environment file or update its override variable. Update custom
   producer and tik scripts to read the GEZHI provider variables.
5. Install the repository package in a clean environment, then verify both
   `gezhi --help` and `python -m gezhi --help`.
6. Run `gezhi validate`, `gezhi doctor`, and `gezhi run --dry-run` before a real
   heartbeat.
7. Install the new scheduler with `gezhi heartbeat install` only after the old
   scheduler artifacts are gone.

## Fail-Closed Checks

GEZHI does not silently create empty state beside earlier durable state. It also
refuses to install a second scheduler over detected earlier scheduler artifacts
or to run a repository transaction while an earlier repository lock is active.
These checks prevent split state and concurrent mutation. Resolve the reported
path or service explicitly, then rerun the command.

State migration is intentionally manual. Back up the project before moving
durable state, and inspect `gezhi state` after validation to confirm that the
expected history and goal binding are present.
