# gh-actions-cli

Interactive Python CLI for running GitHub Actions workflows, checking workflow run status, browsing jobs and steps, reading logs, and downloading artifacts.

Russian documentation: [README.ru.md](README.ru.md)

## Requirements

- Python 3.11+
- GitHub PAT in `GITHUB_PAT`
- Repository in `GITHUB_REPOSITORY` as `owner/repo`

## Installation

```bash
python3 -m venv .venv
./.venv/bin/pip install -e '.[dev]'
```

## Environment

```bash
export GITHUB_PAT=ghp_xxx
export GITHUB_REPOSITORY=owner/repo
```

Optional:

| Variable | Default | Description |
| --- | --- | --- |
| `GITHUB_API_URL` | `https://api.github.com` | GitHub API base URL. |
| `GH_ACTIONS_POLL_INTERVAL` | `5` | Polling interval in seconds for `/follow` and `/follow-logs`. |
| `GH_ACTIONS_DEFAULT_BRANCH` | — | Fallback branch when GitHub does not return the default branch. |
| `GH_ACTIONS_AI_COMMAND` | `codex` | CLI tool used by `/diagnose`. Must accept the prompt as a final positional argument. |
| `GH_ACTIONS_AI_COMMAND_ARGS` | `exec --skip-git-repo-check --color never` | Space-separated arguments placed before the prompt. Default is tuned for `codex`. Set to `-p` when using `claude`. |
| `GH_ACTIONS_DIAGNOSE_DIR` | `~/.gh-actions-diagnoses` | Directory where `/diagnose` saves Markdown reports. |
| `GH_ACTIONS_MAX_LOG_LINES` | `150` | Maximum log lines per job sent to the AI tool. |
| `GH_ACTIONS_AI_TIMEOUT` | `120` | Timeout in seconds for the AI subprocess call. |

## Run

```bash
python -m gh_actions_cli
```

or, after installing the script entry point:

```bash
gh-actions-cli
```

## Keyboard Shortcuts

- `Ctrl+\` - stop the currently running command on macOS/Linux and return to the prompt
- `Ctrl+C` - exit the CLI

## Command Format

Every command starts with `/`. Arguments are split like a shell command, so quoted values are supported:

```text
/run build.yml ref=main message="release candidate"
```

Tokens in `key=value` form are parsed as options. Other tokens are positional arguments.

## Commands

| Command | Description |
| --- | --- |
| `/help` | Show command help. |
| `/workflows` | List repository workflows and store numeric indexes for later commands. |
| `/workflow <workflow>` | Show one workflow's details. |
| `/dispatch-inputs <workflow>` | Show `workflow_dispatch` inputs declared in a workflow file. |
| `/run <workflow> [ref=...] [defer=...] [poll=10] [key=value ...]` | Dispatch a workflow. `ref` selects the branch/tag/SHA. `defer` enables deferred dispatch (see [Deferred dispatch](#deferred-dispatch)). Every other `key=value` option is sent as a workflow input. |
| `/run-form <workflow>` | Dispatch a workflow through interactive prompts based on its `workflow_dispatch` inputs. |
| `/runs <workflow> [limit=10]` | List recent runs for a workflow. `limit` controls how many runs are requested. |
| `/run-status <run-id>` | Show status and conclusion for one run. |
| `/follow <run-id> [diagnose=true]` | Poll one run until it completes. With `diagnose=true`, automatically runs `/diagnose` if the run fails. Stop only this command with `Ctrl+\`. |
| `/jobs <run-id>` | List jobs for a run and store numeric indexes for later job commands. |
| `/steps <job-id>` | List steps for a job. |
| `/logs <job-id> [file=...] [no_print=true]` | Print a whole job log. `file` saves the log locally. `no_print=true` saves without printing the log body. |
| `/step-log <job-id> <step> [file=...] [no_print=true]` | Print one step log by step number or step name. `file` and `no_print=true` work the same as in `/logs`. |
| `/follow-logs <job-id>` | Poll and print new job log output until the run completes. Stop only this command with `Ctrl+\`. |
| `/artifacts <run-id>` | List artifacts for a run and store numeric indexes for `/download-artifacts`. |
| `/download-artifacts <run-id> <artifact...> [dir=...]` | Download selected artifacts. Selectors can be `all`, an index from the last `/artifacts` output, an artifact id, or an artifact name. `dir` sets the target directory. |
| `/cancel-run <run-id>` | Ask GitHub to cancel a workflow run. |
| `/run-args <run-id>` | Show saved dispatch arguments for runs started in the current CLI session, or best-effort GitHub metadata for other runs. |
| `/runner-load [limit=100]` | Show a rough runner load estimate for the repository: overall queued/in-progress counts, a simple pressure label, and a workflow breakdown. |
| `/diagnose <run-id>` | Fetch failed job logs, call the configured AI tool as a subprocess, and save a Markdown analysis report to `GH_ACTIONS_DIAGNOSE_DIR`. Nothing is printed to the terminal except the saved file path. |
| `/clear` | Clear the terminal. |
| `/quit` | Exit the CLI. |

## Selectors

`<workflow>` can be:

- a numeric GitHub workflow id
- an index from the last `/workflows` output
- a workflow file name, for example `build.yml`

`<run-id>` can be:

- a numeric GitHub workflow run id
- an index from the last `/runs` output

`<job-id>` can be:

- an index from the last `/jobs` output

`<artifact>` in `/download-artifacts` can be:

- `all` to download every artifact from the run
- an index from the last `/artifacts` output
- a numeric artifact id
- an artifact name

## Options

| Option | Used by | Description |
| --- | --- | --- |
| `ref=...` | `/run` | Branch, tag, or SHA used to dispatch the workflow. Defaults to `GH_ACTIONS_DEFAULT_BRANCH`, then the repository default branch, then `main`. |
| `defer=idle` | `/run` | Wait until runners are free (pressure = "free"), then dispatch. |
| `defer=TIME` | `/run` | Dispatch at a specific wall-clock time. Accepted formats: `11pm`, `11:30pm`, `23:00`. If the time has already passed today, the next day is used. |
| `defer=TIME,idle` | `/run` | Start the idle-check loop at the given time, then dispatch when runners are free. |
| `poll=N` | `/run` | Polling interval in minutes for `defer=idle`. Defaults to `10`. |
| `diagnose=true` | `/follow` | Automatically run `/diagnose` after the run finishes with `failure`. |
| `key=value` | `/run` | Workflow input passed to GitHub. All options except `ref`, `defer`, and `poll` are treated as inputs. |
| `limit=10` | `/runs` | Number of workflow runs to request. |
| `file=/path/to/file.log` | `/logs`, `/step-log` | Save output to a local file. Parent directories are created automatically. |
| `no_print=true` | `/logs`, `/step-log` | Do not print the log body to the terminal. Accepted true values are `1`, `true`, `yes`, and `on`. |
| `dir=/path/to/save` | `/download-artifacts` | Directory where artifacts are extracted. Defaults to `artifacts/run-<run-id>`. |
| `limit=100` | `/runner-load` | How many recent repository runs to inspect when estimating current load. |

## Deferred dispatch

The `defer=` option on `/run` lets you schedule a workflow dispatch without blocking your terminal.

```text
# Dispatch as soon as runners are free (checked every 10 minutes)
/run 1 ref=main defer=idle

# Custom polling interval (every 5 minutes)
/run deploy.yml ref=release defer=idle poll=5

# Dispatch at exactly 11 pm tonight
/run 1 ref=main defer=11pm
/run 1 ref=main defer=23:00

# Start the idle-check loop at 11 pm, dispatch when runners are free
/run 1 ref=main defer=11pm,idle

# Works with workflow inputs too — defer and poll are not sent as inputs
/run 1 ref=develop defer=idle dry_run=true environment=staging
```

The command prints a single status line while waiting (e.g. *"Runners busy (queued: 2, in_progress: 1), next check in 10 min..."*) and confirms dispatch once the workflow is sent. Stop the wait at any time with `Ctrl+\`.

## AI failure diagnosis

`/diagnose` calls a local AI CLI tool to analyse failed job logs and saves a Markdown report — nothing is dumped to the terminal.

```text
# Analyse a run that has already failed
/diagnose 301
/diagnose 1          # index from the last /runs output

# Watch a run and diagnose automatically if it fails
/follow 1 diagnose=true
/follow 123456789 diagnose=true
```

The report is saved to `~/.gh-actions-diagnoses/<run-id>-<workflow>-<timestamp>.md` (override with `GH_ACTIONS_DIAGNOSE_DIR`). Example content:

```markdown
# Failure analysis: Build #301
Date: 2026-05-28 23:15:00
Branch: main

---

**test**
- Cause: unit tests failed in the auth module
- Failure point: pytest src/auth/test_login.py::test_token_refresh
- Recommendation: check the refresh_token mock at line 47
```

**Changing the AI tool.** By default the command calls `codex exec --skip-git-repo-check --color never`. To use `claude`:

```bash
export GH_ACTIONS_AI_COMMAND=claude
export GH_ACTIONS_AI_COMMAND_ARGS="-p"
```

The tool must accept the full prompt as a final positional argument and write its response to stdout.

## Examples

```text
/workflows
/dispatch-inputs 2
/run 2 ref=main dry_run=true
/run build.yml ref=release message="release candidate"
/run 2 ref=main defer=idle
/run 2 ref=main defer=11pm,idle dry_run=true
/runs 2 limit=5
/jobs 1
/steps 1
/step-log 1 2
/logs 1 file=~/Downloads/job.log
/step-log 1 "Checkout" file=~/Downloads/checkout.log
/logs 1 file=~/Downloads/job.log no_print=true
/follow 123456789
/follow 123456789 diagnose=true
/diagnose 123456789
/artifacts 123456789
/download-artifacts 123456789 all
/download-artifacts 123456789 eval-agent-result
/download-artifacts 123456789 1 dir=~/Downloads/gh-actions
/cancel-run 123456789
/run-args 123456789
/runner-load
/runner-load limit=200
```

## Notes

- Manual workflow dispatch is supported only for workflows with `workflow_dispatch`.
- Workflow inputs are read directly from the workflow YAML file on GitHub.
- GitHub does not expose step logs as a separate API resource. `/step-log` uses best-effort parsing of the job log and falls back to the full job log when needed.
- Artifacts are downloaded and extracted locally under `artifacts/run-<run-id>/...` unless `dir=...` is provided.
- `/run-args` shows exact `ref` and inputs only for runs started by this CLI in the current session. For other runs it shows best-effort metadata from the GitHub API.
- `/runner-load` is a heuristic based on repository run statuses. It does not know the real global capacity of GitHub-hosted runners.
