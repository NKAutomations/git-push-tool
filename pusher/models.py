from dataclasses import dataclass, field
from pathlib import Path
from threading import Event


class AppError(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class Cancelled(AppError):
    def __init__(self):
        super().__init__('cancelled', 'Abgebrochen. Bereits abgeschlossene Schritte bleiben erhalten.', True)


def checkpoint(cancel):
    if cancel.is_set():
        raise Cancelled()


@dataclass(frozen=True)
class StepResult:
    stage: str
    status: str
    message: str
    url: str = ''
    code: str = ''


@dataclass
class Report:
    steps: list = field(default_factory=list)
    commit: str = ''
    tag: str = ''

    def add(self, stage, status, message, url='', code=''):
        self.steps.append(StepResult(stage, status, message, url, code))

    @property
    def outcome(self):
        failed = any(s.status in ('failed', 'cancelled', 'blocked') for s in self.steps)
        success = any(s.status == 'success' for s in self.steps)
        return ('partial' if success else 'failed') if failed else 'success'


@dataclass(frozen=True)
class PushOptions:
    project: Path
    remote: str
    branch: str
    message: str
    tag: str = ''
    tag_message: str = ''
    mode: str = 'safe'
    allow_unrelated: bool = False


@dataclass(frozen=True)
class ReleaseOptions:
    tag: str
    title: str
    notes: str
    update: bool = False
    draft: bool = False
    prerelease: bool = False


@dataclass(frozen=True)
class Release:
    id: str
    tag: str
    title: str
    notes: str
    url: str
    upload_url: str = ''
    draft: bool = False
    prerelease: bool = False


@dataclass(frozen=True)
class Asset:
    id: str
    name: str
    size: int
    url: str
    digest: str = ''
    state: str = 'uploaded'
