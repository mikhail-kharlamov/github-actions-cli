# gh-actions-cli

Интерактивный Python CLI для запуска GitHub workflows, просмотра статусов run/job/step и чтения логов.

## Требования

- Python 3.11+
- GitHub PAT в `GITHUB_PAT`
- репозиторий в `GITHUB_REPOSITORY` в формате `owner/repo`

## Установка

```bash
python3 -m venv .venv
./.venv/bin/pip install -e '.[dev]'
```

## Переменные окружения

```bash
export GITHUB_PAT=ghp_xxx
export GITHUB_REPOSITORY=owner/repo
```

Опционально:

- `GITHUB_API_URL` — адрес GitHub API, по умолчанию `https://api.github.com`
- `GH_ACTIONS_POLL_INTERVAL` — интервал polling для `follow`, по умолчанию `5`
- `GH_ACTIONS_DEFAULT_BRANCH` — fallback branch, если GitHub не вернул default branch

## Запуск

```bash
python -m gh_actions_cli
```

или после установки script entrypoint:

```bash
gh-actions-cli
```

## Команды

```text
/help
/workflows
/workflow <workflow>
/dispatch-inputs <workflow>
/run <workflow> [ref=main] [key=value ...]
/run-form <workflow>
/runs <workflow> [limit=10]
/run-status <run-id>
/follow <run-id>
/jobs <run-id>
/steps <job-id>
/logs <job-id>
/step-log <job-id> <step-number-or-name>
/follow-logs <job-id>
/artifacts <run-id>
/download-artifacts <run-id> <artifact...> [dir=/path/to/save]
/clear
/quit
```

`<workflow>` может быть:

- numeric GitHub workflow id
- индексом из последнего вывода `/workflows`
- именем файла, например `build.yml`

`<run-id>` может быть:

- numeric GitHub run id
- индексом из последнего вывода `/runs`

`<job-id>` может быть:

- индексом из последнего вывода `/jobs`

## Примеры

```text
/workflows
/dispatch-inputs 2
/run 2 ref=main dry_run=true
/runs 2 limit=5
/jobs 1
/steps 1
/step-log 1 2
/follow 123456789
/artifacts 123456789
/download-artifacts 123456789 eval-agent-result
/download-artifacts 123456789 1 dir=~/Downloads/gh-actions
```

## Ограничения

- ручной запуск поддерживается только для workflows с `workflow_dispatch`
- inputs читаются напрямую из YAML workflow файла на GitHub
- GitHub не отдает step logs как отдельный API ресурс, поэтому `step-log` использует best-effort разбор job log и при необходимости честно падает в вывод полного job log
- артефакты скачиваются и распаковываются локально в `artifacts/run-<run-id>/...`, если `dir=...` не указан
- если путь из `dir=...` не существует, он создается автоматически
