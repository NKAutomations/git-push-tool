"""API credentials stay in memory; Git uses its own credential helper / SSH."""
import os
import shutil
import subprocess
from .models import AppError


def resolve_token(repository, explicit='', source='environment'):
    if explicit.strip():
        return explicit.strip()
    if source == 'gh':
        if repository.provider != 'GitHub' or not shutil.which('gh'):
            raise AppError('auth', 'GitHub CLI fehlt oder GitHub ist nicht ausgewählt.')
        try:
            result = subprocess.run(['gh', 'auth', 'token', '--hostname', repository.host],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=15, shell=False,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except (OSError, subprocess.TimeoutExpired):
            raise AppError('auth', 'GitHub-CLI-Anmeldung konnte nicht gelesen werden.') from None
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.decode('utf-8').strip()
        raise AppError('auth', 'Zuerst gh auth login für den gewählten Host ausführen.')
    names = ('GH_TOKEN', 'GITHUB_TOKEN') if repository.provider == 'GitHub' else ('GITLAB_TOKEN', 'GLAB_TOKEN')
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    raise AppError('auth', 'API-Token eingeben oder passende Token-Umgebungsvariable setzen. Git-Anmeldung allein reicht für Releases nicht aus.')
