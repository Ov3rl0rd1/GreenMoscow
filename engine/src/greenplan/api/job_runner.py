import multiprocessing
import threading
from collections.abc import Callable
from typing import Protocol

from greenplan.api.job_service import JobService
from greenplan.api.service_factory import ServiceLocation, execute_in_worker

SPAWN_CONTEXT = "spawn"
KILLED_BY_SYSTEM_EXIT_CODES = frozenset({-9, 137})

Worker = Callable[[ServiceLocation, str], None]


class JobRunner(Protocol):
    def run(self, job_id: str) -> None: ...


class InProcessJobRunner:
    def __init__(self, service: JobService) -> None:
        self._service = service
        self._lock = threading.Lock()

    def run(self, job_id: str) -> None:
        with self._lock:
            self._service.execute(job_id)


class IsolatedJobRunner:
    def __init__(
        self, service: JobService, location: ServiceLocation, worker: Worker = execute_in_worker
    ) -> None:
        self._service = service
        self._location = location
        self._worker = worker
        self._lock = threading.Lock()

    def run(self, job_id: str) -> None:
        with self._lock:
            exit_code = self._exit_code_of_worker(job_id)
        if exit_code:
            self._service.fail_unfinished(job_id, crash_message(exit_code))

    def _exit_code_of_worker(self, job_id: str) -> int | None:
        context = multiprocessing.get_context(SPAWN_CONTEXT)
        process = context.Process(target=self._worker, args=(self._location, job_id), daemon=True)
        process.start()
        process.join()
        return process.exitcode


def crash_message(exit_code: int) -> str:
    if exit_code in KILLED_BY_SYSTEM_EXIT_CODES:
        return (
            "Расчёт остановлен системой: процессу не хватило памяти. Выделите сервису больше памяти "
            "или загрузите чертёж без лишних внешних ссылок и запустите задачу заново."
        )
    return f"Процесс расчёта аварийно завершился с кодом {exit_code}. Запустите задачу заново."
