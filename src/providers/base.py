from __future__ import annotations

import logging
import time
from typing import Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import AppConfig
from src.models import Job

LOGGER = logging.getLogger(__name__)


class JobProvider(Protocol):
    name: str

    def fetch(self, config: AppConfig) -> list[Job]: ...


def retrying_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def request_json(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
    auth: tuple[str, str] | None = None,
    timeout: int = 20,
    attempts: int = 3,
) -> dict:
    for attempt in range(attempts):
        try:
            response = session.get(url, params=params, auth=auth, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt == attempts - 1:
                raise
            time.sleep(0.5 * (2**attempt))
    return {}
