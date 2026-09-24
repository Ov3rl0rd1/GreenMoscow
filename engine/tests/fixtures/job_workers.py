import os

from greenplan.api.service_factory import ServiceLocation

CRASH_EXIT_CODE = 3


def crashing_worker(location: ServiceLocation, job_id: str) -> None:
    os._exit(CRASH_EXIT_CODE)
