from __future__ import annotations

SUPPORTED_LANGUAGES = ("ru", "en")
DEFAULT_LANGUAGE = "ru"

_current_language = DEFAULT_LANGUAGE

_HELP_TEXT_RU = """\
/help                        показать список команд
/lang <ru|en>                переключить язык интерфейса (сейчас: {language})
/workflows                   получить список workflow
/workflow <workflow>         показать детали workflow
/dispatch-inputs <workflow>  показать workflow_dispatch inputs
/run <workflow> [ref=...] [defer=idle|TIME|TIME,idle] [poll=10] [key=value ...]
  defer=idle          — ждать, пока раннеры свободны, затем запустить
  defer=11pm          — запустить ровно в указанное время (11pm / 23:00 / 11:30pm)
  defer=11pm,idle     — начать проверку раннеров с указанного времени
  poll=N              — интервал проверки в минутах (по умолчанию 10)
/run-form <workflow>         интерактивный запуск workflow
/runs <workflow> [limit=10]  последние run-ы workflow
/run-status <run-id>         статус run; если ещё выполняется — на каком шаге каждая джоба
/follow <run-id> [diagnose=true]  следить за статусом run; при падении авто-запускает /diagnose
/jobs <run-id>               jobs конкретного run
/steps <job-id>              steps конкретного job
/logs <job-id>               лог job целиком
/step-log <job-id> <step>    лог одного шага
/follow-logs <job-id>        обновлять лог job до завершения
/artifacts <run-id>          список артефактов run
/download-artifacts <run-id> <artifact...> [dir=...]  скачать выбранные артефакты
/cancel-run <run-id>         остановить run
/run-args <run-id>           показать аргументы запуска run
/runner-load [limit=100]     показать текущую загрузку раннеров по репозиторию
/diagnose <run-id>           AI-анализ упавших джобов, сохраняет отчёт в файл
/clear                       очистить экран
/quit                        выйти

Переменные окружения для диагностики:
  GH_ACTIONS_AI_COMMAND      команда AI-инструмента (по умолч. codex)
  GH_ACTIONS_AI_COMMAND_ARGS аргументы перед промптом (по умолч. exec --skip-git-repo-check --color never)
  GH_ACTIONS_DIAGNOSE_DIR    куда сохранять отчёты (по умолч. ~/.gh-actions-diagnoses)
  GH_ACTIONS_MAX_LOG_LINES   строк лога на джобу (по умолч. 150)
  GH_ACTIONS_AI_TIMEOUT      таймаут в секундах (по умолч. 120)
  GH_ACTIONS_LANG            язык интерфейса ru|en (по умолч. ru)

Горячие клавиши:
Ctrl+\\                      остановить текущую команду на macOS/Linux
Ctrl+C                       выйти из CLI
"""

_HELP_TEXT_EN = """\
/help                        show the command list
/lang <ru|en>                switch the interface language (current: {language})
/workflows                   list workflows
/workflow <workflow>         show workflow details
/dispatch-inputs <workflow>  show workflow_dispatch inputs
/run <workflow> [ref=...] [defer=idle|TIME|TIME,idle] [poll=10] [key=value ...]
  defer=idle          — wait until runners are free, then dispatch
  defer=11pm          — dispatch at exactly the given time (11pm / 23:00 / 11:30pm)
  defer=11pm,idle     — start checking runners from the given time
  poll=N              — check interval in minutes (default 10)
/run-form <workflow>         interactive workflow dispatch
/runs <workflow> [limit=10]  recent runs of a workflow
/run-status <run-id>         run status; if still running — the current step of each job
/follow <run-id> [diagnose=true]  follow a run's status; auto-runs /diagnose on failure
/jobs <run-id>               jobs of a given run
/steps <job-id>               steps of a given job
/logs <job-id>               full log of a job
/step-log <job-id> <step>    log of a single step
/follow-logs <job-id>        keep updating a job's log until it finishes
/artifacts <run-id>          list a run's artifacts
/download-artifacts <run-id> <artifact...> [dir=...]  download selected artifacts
/cancel-run <run-id>         cancel a run
/run-args <run-id>           show the dispatch arguments of a run
/runner-load [limit=100]     show the repository's current runner load
/diagnose <run-id>           AI analysis of failed jobs, saves a report to a file
/clear                       clear the screen
/quit                        quit

Environment variables for diagnosis:
  GH_ACTIONS_AI_COMMAND      AI tool command (default: codex)
  GH_ACTIONS_AI_COMMAND_ARGS arguments before the prompt (default: exec --skip-git-repo-check --color never)
  GH_ACTIONS_DIAGNOSE_DIR    where to save reports (default: ~/.gh-actions-diagnoses)
  GH_ACTIONS_MAX_LOG_LINES   log lines per job (default: 150)
  GH_ACTIONS_AI_TIMEOUT      timeout in seconds (default: 120)
  GH_ACTIONS_LANG            interface language ru|en (default: ru)

Hotkeys:
Ctrl+\\                      stop the current command on macOS/Linux
Ctrl+C                       quit the CLI
"""

_MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "help.text": _HELP_TEXT_RU,
        "lang.switched": "Язык интерфейса: {language}.",
        "lang.invalid": "Неизвестный язык: {language!r}. Доступно: {available}.",
        "dispatch_inputs.none": "У workflow нет workflow_dispatch inputs.",
        "dispatch.sent_with_ref": "Workflow {name} отправлен с ref={ref}.",
        "defer.bad_time": "Не удалось распознать время: {part!r}. Используйте формат 11pm, 11:30pm или 23:00.",
        "defer.missing": "Укажите defer=idle, defer=11pm или defer=11pm,idle.",
        "defer.waiting_until": "Отложенный запуск: ожидание до {time} (Ctrl+\\ для отмены)...",
        "defer.waiting_idle": "Ожидание свободных раннеров (интервал: {minutes} мин)...",
        "defer.runners_free": "Раннеры свободны — отправляю.",
        "defer.runners_busy": (
            "Раннеры заняты (queued: {queued}, in_progress: {in_progress}), "
            "следующая проверка через {minutes} мин..."
        ),
        "run_form.no_inputs": "У workflow нет workflow_dispatch inputs для интерактивного запуска.",
        "run_form.ref_prompt": "ref (Enter для default branch): ",
        "run_form.field_required": "Поле {name} обязательно.",
        "run_form.dispatched": "Workflow {name} отправлен.",
        "job.not_found": "Job {id} не найден.",
        "job.log_not_found": "Для job {id} не удалось найти лог.",
        "job.required": "Нужно указать job.",
        "job.invalid_token": "Job должен быть индексом из последнего списка /jobs.",
        "steplog.args_required": "Нужно указать job и step.",
        "steplog.fallback": "Не удалось точно выделить шаг {name}, показываю лог job целиком.",
        "artifacts.args_required": "Нужно указать run и хотя бы один артефакт или all.",
        "artifacts.downloaded_header": "Скачано:\n",
        "cancel.sent": "Run {id} отправлен на остановку.",
        "run_args.no_inputs_hint": "  GitHub API не возвращает workflow_dispatch inputs для чужих run в явном виде.",
        "diagnose.none_failed": "Run {id}: упавших джобов не найдено.",
        "diagnose.downloading": "Упавших джобов: {count}. Скачиваю логи...",
        "diagnose.running_ai": "Запускаю AI-анализ [{command}]...",
        "diagnose.saved": "Анализ сохранён: {path}",
        "diagnose.prompt.intro": "Ты — инженер DevOps. Ниже логи упавших джобов из GitHub Actions.",
        "diagnose.prompt.instruction": "Проанализируй причины каждого падения и составь краткий отчёт строго на русском языке.",
        "diagnose.prompt.workflow_label": "Воркфлоу: {name}",
        "diagnose.prompt.branch_label": "Ветка: {branch}",
        "diagnose.prompt.run_label": "Ран: #{id}",
        "diagnose.prompt.job_header": "== Джоба: {name} ==",
        "diagnose.prompt.job_status": "Статус: {conclusion}",
        "diagnose.prompt.job_failed_step": "Упавший шаг: {step}",
        "diagnose.prompt.job_log_header": "--- Лог (последние {n} строк) ---",
        "diagnose.prompt.log_unavailable": "(лог недоступен)",
        "diagnose.prompt.format_intro": "Формат ответа — для каждой джобы:",
        "diagnose.prompt.format_name": "**<название джобы>**",
        "diagnose.prompt.format_reason": "- Причина: <краткое объяснение>",
        "diagnose.prompt.format_failure_point": "- Точка отказа: <файл/команда/шаг>",
        "diagnose.prompt.format_recommendation": "- Рекомендация: <что исправить>",
        "ai.not_found": "AI-инструмент не найден: {command!r}. Проверьте GH_ACTIONS_AI_COMMAND.",
        "ai.timeout": "AI-инструмент не ответил за {seconds} сек. Увеличьте GH_ACTIONS_AI_TIMEOUT.",
        "ai.no_output": "(нет вывода)",
        "ai.failed": "AI-инструмент завершился с ошибкой: {detail}",
        "report.title": "# Анализ падения: {name} #{id}",
        "report.date": "Дата: {date}",
        "report.branch": "Ветка: {branch}",
        "logs.saved": "Лог сохранен в {path}",
        "workflow.required": "Нужно указать workflow.",
        "workflow.not_found": "Workflow {token} не найден.",
        "run.required": "Нужно указать run.",
        "run.invalid_token": "Run должен быть numeric id или индексом из последнего списка.",
        "artifact.not_found": "Артефакт {selector} не найден.",
        "input.boolean_invalid": "Boolean input должен быть true или false.",
        "input.choice_invalid": "Допустимые значения: {options}",
        "pressure.overloaded": "Перегружено",
        "pressure.moderate": "Умеренно",
        "pressure.free": "Свободно",
        "runner_load.assessment": "Оценка: {pressure}",
        "error.title": "Ошибка",
        "repl.welcome": r"Введите /help для списка команд. Ctrl+\ останавливает текущую команду, Ctrl+C выходит.",
        "repl.command_stopped": "\nКоманда остановлена.",
        "command.must_start_with_slash": "Команда должна начинаться с /.",
        "command.empty": "Пустая команда.",
        "command.unknown": "Неизвестная команда: {name}",
        "config.missing_pat": "Требуется переменная окружения GITHUB_PAT.",
        "config.missing_repo": "Требуется переменная окружения GITHUB_REPOSITORY.",
        "config.bad_repo_format": "GITHUB_REPOSITORY должен быть в формате owner/repo.",
        "workflow_parser.parse_failed": "Не удалось распарсить workflow YAML.",
        "logs.archive_read_failed": "Не удалось прочитать архив логов GitHub.",
    },
    "en": {
        "help.text": _HELP_TEXT_EN,
        "lang.switched": "Interface language: {language}.",
        "lang.invalid": "Unknown language: {language!r}. Available: {available}.",
        "dispatch_inputs.none": "This workflow has no workflow_dispatch inputs.",
        "dispatch.sent_with_ref": "Workflow {name} dispatched with ref={ref}.",
        "defer.bad_time": "Could not parse time: {part!r}. Use the format 11pm, 11:30pm or 23:00.",
        "defer.missing": "Specify defer=idle, defer=11pm or defer=11pm,idle.",
        "defer.waiting_until": "Deferred dispatch: waiting until {time} (Ctrl+\\ to cancel)...",
        "defer.waiting_idle": "Waiting for free runners (check interval: {minutes} min)...",
        "defer.runners_free": "Runners are free — dispatching.",
        "defer.runners_busy": (
            "Runners are busy (queued: {queued}, in_progress: {in_progress}), "
            "next check in {minutes} min..."
        ),
        "run_form.no_inputs": "This workflow has no workflow_dispatch inputs for interactive dispatch.",
        "run_form.ref_prompt": "ref (Enter for default branch): ",
        "run_form.field_required": "Field {name} is required.",
        "run_form.dispatched": "Workflow {name} dispatched.",
        "job.not_found": "Job {id} not found.",
        "job.log_not_found": "Could not find a log for job {id}.",
        "job.required": "You must specify a job.",
        "job.invalid_token": "Job must be an index from the latest /jobs list.",
        "steplog.args_required": "You must specify job and step.",
        "steplog.fallback": "Could not isolate step {name} precisely — showing the full job log instead.",
        "artifacts.args_required": "You must specify a run and at least one artifact, or 'all'.",
        "artifacts.downloaded_header": "Downloaded:\n",
        "cancel.sent": "Run {id} cancellation requested.",
        "run_args.no_inputs_hint": "  GitHub API does not expose workflow_dispatch inputs for runs you didn't dispatch.",
        "diagnose.none_failed": "Run {id}: no failed jobs found.",
        "diagnose.downloading": "Failed jobs: {count}. Downloading logs...",
        "diagnose.running_ai": "Running AI analysis [{command}]...",
        "diagnose.saved": "Analysis saved: {path}",
        "diagnose.prompt.intro": "You are a DevOps engineer. Below are the logs of failed jobs from GitHub Actions.",
        "diagnose.prompt.instruction": "Analyze the cause of each failure and write a concise report strictly in English.",
        "diagnose.prompt.workflow_label": "Workflow: {name}",
        "diagnose.prompt.branch_label": "Branch: {branch}",
        "diagnose.prompt.run_label": "Run: #{id}",
        "diagnose.prompt.job_header": "== Job: {name} ==",
        "diagnose.prompt.job_status": "Status: {conclusion}",
        "diagnose.prompt.job_failed_step": "Failed step: {step}",
        "diagnose.prompt.job_log_header": "--- Log (last {n} lines) ---",
        "diagnose.prompt.log_unavailable": "(log unavailable)",
        "diagnose.prompt.format_intro": "Response format — for each job:",
        "diagnose.prompt.format_name": "**<job name>**",
        "diagnose.prompt.format_reason": "- Cause: <brief explanation>",
        "diagnose.prompt.format_failure_point": "- Failure point: <file/command/step>",
        "diagnose.prompt.format_recommendation": "- Recommendation: <what to fix>",
        "ai.not_found": "AI tool not found: {command!r}. Check GH_ACTIONS_AI_COMMAND.",
        "ai.timeout": "AI tool did not respond within {seconds} sec. Increase GH_ACTIONS_AI_TIMEOUT.",
        "ai.no_output": "(no output)",
        "ai.failed": "AI tool exited with an error: {detail}",
        "report.title": "# Failure analysis: {name} #{id}",
        "report.date": "Date: {date}",
        "report.branch": "Branch: {branch}",
        "logs.saved": "Log saved to {path}",
        "workflow.required": "You must specify a workflow.",
        "workflow.not_found": "Workflow {token} not found.",
        "run.required": "You must specify a run.",
        "run.invalid_token": "Run must be a numeric id or an index from the latest list.",
        "artifact.not_found": "Artifact {selector} not found.",
        "input.boolean_invalid": "Boolean input must be true or false.",
        "input.choice_invalid": "Allowed values: {options}",
        "pressure.overloaded": "Overloaded",
        "pressure.moderate": "Moderate",
        "pressure.free": "Free",
        "runner_load.assessment": "Assessment: {pressure}",
        "error.title": "Error",
        "repl.welcome": r"Type /help for the command list. Ctrl+\ stops the current command, Ctrl+C exits.",
        "repl.command_stopped": "\nCommand stopped.",
        "command.must_start_with_slash": "Command must start with /.",
        "command.empty": "Empty command.",
        "command.unknown": "Unknown command: {name}",
        "config.missing_pat": "The GITHUB_PAT environment variable is required.",
        "config.missing_repo": "The GITHUB_REPOSITORY environment variable is required.",
        "config.bad_repo_format": "GITHUB_REPOSITORY must be in the owner/repo format.",
        "workflow_parser.parse_failed": "Failed to parse workflow YAML.",
        "logs.archive_read_failed": "Failed to read the GitHub logs archive.",
    },
}


def get_language() -> str:
    return _current_language


def set_language(language: str) -> None:
    global _current_language
    normalized = language.strip().lower()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError(t("lang.invalid", language=language, available=", ".join(SUPPORTED_LANGUAGES)))
    _current_language = normalized


def t(key: str, **kwargs: object) -> str:
    catalog = _MESSAGES.get(_current_language) or _MESSAGES[DEFAULT_LANGUAGE]
    template = catalog.get(key) or _MESSAGES[DEFAULT_LANGUAGE][key]
    return template.format(**kwargs) if kwargs else template
