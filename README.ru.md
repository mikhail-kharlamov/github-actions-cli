# gh-actions-cli

Интерактивный Python CLI для запуска GitHub Actions workflows, просмотра статусов run/job/step, чтения логов и скачивания артефактов.

Основная документация на английском: [README.md](README.md)

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

- `GITHUB_API_URL` - адрес GitHub API, по умолчанию `https://api.github.com`
- `GH_ACTIONS_POLL_INTERVAL` - интервал polling для `/follow` и `/follow-logs`, по умолчанию `5`
- `GH_ACTIONS_DEFAULT_BRANCH` - fallback branch, если GitHub не вернул default branch

## Запуск

```bash
python -m gh_actions_cli
```

или после установки script entrypoint:

```bash
gh-actions-cli
```

## Горячие клавиши

- `Ctrl+\` - остановить текущую команду на macOS/Linux и вернуться к prompt
- `Ctrl+C` - выйти из CLI целиком

## Формат команд

Каждая команда начинается с `/`. Аргументы разбираются как shell-команда, поэтому значения с пробелами можно брать в кавычки:

```text
/run build.yml ref=main message="release candidate"
```

Токены вида `key=value` считаются опциями. Остальные токены считаются позиционными аргументами.

## Команды

| Команда | Описание |
| --- | --- |
| `/help` | Показать справку по командам. |
| `/workflows` | Получить список workflows репозитория и сохранить numeric indexes для следующих команд. |
| `/workflow <workflow>` | Показать детали одного workflow. |
| `/dispatch-inputs <workflow>` | Показать `workflow_dispatch` inputs из workflow файла. |
| `/run <workflow> [ref=...] [key=value ...]` | Запустить workflow. `ref` выбирает branch/tag/SHA. Все остальные `key=value` опции отправляются как workflow inputs. |
| `/run-form <workflow>` | Интерактивно запустить workflow через prompts на основе `workflow_dispatch` inputs. |
| `/runs <workflow> [limit=10]` | Показать последние run-ы workflow. `limit` задает количество запрошенных run-ов. |
| `/run-status <run-id>` | Показать status и conclusion одного run. |
| `/follow <run-id>` | Следить за run до завершения. Остановить только эту команду можно через `Ctrl+\`. |
| `/jobs <run-id>` | Показать jobs run-а и сохранить numeric indexes для команд по job. |
| `/steps <job-id>` | Показать steps job-а. |
| `/logs <job-id> [file=...] [no_print=true]` | Напечатать лог job целиком. `file` сохраняет лог локально. `no_print=true` сохраняет без вывода тела лога в терминал. |
| `/step-log <job-id> <step> [file=...] [no_print=true]` | Напечатать лог одного step по номеру или имени. `file` и `no_print=true` работают как в `/logs`. |
| `/follow-logs <job-id>` | Следить за логом job до завершения run-а. Остановить только эту команду можно через `Ctrl+\`. |
| `/artifacts <run-id>` | Показать артефакты run-а и сохранить numeric indexes для `/download-artifacts`. |
| `/download-artifacts <run-id> <artifact...> [dir=...]` | Скачать выбранные артефакты. Selectors: `all`, индекс из последнего `/artifacts`, artifact id или artifact name. `dir` задает папку назначения. |
| `/cancel-run <run-id>` | Попросить GitHub остановить workflow run. |
| `/run-args <run-id>` | Показать сохраненные аргументы запуска для run-ов, запущенных в текущей CLI-сессии, или best-effort metadata GitHub для остальных run-ов. |
| `/runner-load [limit=100]` | Показать примерную загрузку раннеров по репозиторию: общие counts queued/in-progress, простую оценку нагрузки и разбивку по workflow. |
| `/clear` | Очистить терминал. |
| `/quit` | Выйти из CLI. |

## Selectors

`<workflow>` может быть:

- numeric GitHub workflow id
- индексом из последнего вывода `/workflows`
- именем файла workflow, например `build.yml`

`<run-id>` может быть:

- numeric GitHub workflow run id
- индексом из последнего вывода `/runs`

`<job-id>` может быть:

- индексом из последнего вывода `/jobs`

`<artifact>` в `/download-artifacts` может быть:

- `all`, чтобы скачать все артефакты run-а
- индексом из последнего вывода `/artifacts`
- numeric artifact id
- именем artifact

## Опции

| Опция | Где используется | Описание |
| --- | --- | --- |
| `ref=...` | `/run` | Branch, tag или SHA для workflow dispatch. По умолчанию используется `GH_ACTIONS_DEFAULT_BRANCH`, затем default branch репозитория, затем `main`. |
| `key=value` | `/run` | Workflow input для GitHub. Все опции кроме `ref` считаются inputs. |
| `limit=10` | `/runs` | Количество workflow run-ов для запроса. |
| `file=/path/to/file.log` | `/logs`, `/step-log` | Сохранить вывод в локальный файл. Родительские директории создаются автоматически. |
| `no_print=true` | `/logs`, `/step-log` | Не печатать тело лога в терминал. True values: `1`, `true`, `yes`, `on`. |
| `dir=/path/to/save` | `/download-artifacts` | Папка, куда распаковать артефакты. По умолчанию `artifacts/run-<run-id>`. |
| `limit=100` | `/runner-load` | Сколько последних run-ов репозитория анализировать для оценки текущей нагрузки. |

## Примеры

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
/runner-load
/runner-load limit=200
```

## Ограничения

- Ручной запуск поддерживается только для workflows с `workflow_dispatch`.
- Inputs читаются напрямую из YAML workflow файла на GitHub.
- GitHub не отдает step logs как отдельный API resource. `/step-log` использует best-effort разбор job log и при необходимости падает в вывод полного job log.
- Артефакты скачиваются и распаковываются локально в `artifacts/run-<run-id>/...`, если `dir=...` не указан.
- `/run-args` точно показывает `ref` и inputs только для запусков, инициированных этим CLI в текущей сессии. Для чужих run выводится best-effort metadata из GitHub API.
- `/runner-load` использует эвристику по статусам run-ов репозитория и не знает реальную глобальную емкость GitHub-hosted runner-ов.
