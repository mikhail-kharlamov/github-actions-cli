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

- `GITHUB_API_URL` - GitHub API URL, defaults to `https://api.github.com`
- `GH_ACTIONS_POLL_INTERVAL` - polling interval for `/follow` and `/follow-logs`, defaults to `5`
- `GH_ACTIONS_DEFAULT_BRANCH` - fallback branch when GitHub does not return the default branch

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
| `/run <workflow> [ref=...] [key=value ...]` | Dispatch a workflow. `ref` selects the branch/tag/SHA. Every other `key=value` option is sent as a workflow input. |
| `/run-form <workflow>` | Dispatch a workflow through interactive prompts based on its `workflow_dispatch` inputs. |
| `/runs <workflow> [limit=10]` | List recent runs for a workflow. `limit` controls how many runs are requested. |
| `/run-status <run-id>` | Show status and conclusion for one run. |
| `/follow <run-id>` | Poll one run until it completes. Stop only this command with `Ctrl+\`. |
| `/jobs <run-id>` | List jobs for a run and store numeric indexes for later job commands. |
| `/steps <job-id>` | List steps for a job. |
| `/logs <job-id> [file=...] [no_print=true]` | Print a whole job log. `file` saves the log locally. `no_print=true` saves without printing the log body. |
| `/step-log <job-id> <step> [file=...] [no_print=true]` | Print one step log by step number or step name. `file` and `no_print=true` work the same as in `/logs`. |
| `/follow-logs <job-id>` | Poll and print new job log output until the run completes. Stop only this command with `Ctrl+\`. |
| `/artifacts <run-id>` | List artifacts for a run and store numeric indexes for `/download-artifacts`. |
| `/download-artifacts <run-id> <artifact...> [dir=...]` | Download selected artifacts. Selectors can be `all`, an index from the last `/artifacts` output, an artifact id, or an artifact name. `dir` sets the target directory. |
| `/cancel-run <run-id>` | Ask GitHub to cancel a workflow run. |
| `/run-args <run-id>` | Show saved dispatch arguments for runs started in the current CLI session, or best-effort GitHub metadata for other runs. |
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
| `key=value` | `/run` | Workflow input passed to GitHub. All options except `ref` are treated as inputs. |
| `limit=10` | `/runs` | Number of workflow runs to request. |
| `file=/path/to/file.log` | `/logs`, `/step-log` | Save output to a local file. Parent directories are created automatically. |
| `no_print=true` | `/logs`, `/step-log` | Do not print the log body to the terminal. Accepted true values are `1`, `true`, `yes`, and `on`. |
| `dir=/path/to/save` | `/download-artifacts` | Directory where artifacts are extracted. Defaults to `artifacts/run-<run-id>`. |

## Examples

```text
/workflows
/dispatch-inputs 2
/run 2 ref=main dry_run=true
/run build.yml ref=release message="release candidate"
/runs 2 limit=5
/jobs 1
/steps 1
/step-log 1 2
/logs 1 file=~/Downloads/job.log
/step-log 1 "Checkout" file=~/Downloads/checkout.log
/logs 1 file=~/Downloads/job.log no_print=true
/follow 123456789
/artifacts 123456789
/download-artifacts 123456789 all
/download-artifacts 123456789 eval-agent-result
/download-artifacts 123456789 1 dir=~/Downloads/gh-actions
/cancel-run 123456789
/run-args 123456789
```

## Notes

- Manual workflow dispatch is supported only for workflows with `workflow_dispatch`.
- Workflow inputs are read directly from the workflow YAML file on GitHub.
- GitHub does not expose step logs as a separate API resource. `/step-log` uses best-effort parsing of the job log and falls back to the full job log when needed.
- Artifacts are downloaded and extracted locally under `artifacts/run-<run-id>/...` unless `dir=...` is provided.
- `/run-args` shows exact `ref` and inputs only for runs started by this CLI in the current session. For other runs it shows best-effort metadata from the GitHub API.
