import re
from dataclasses import dataclass
from urllib.parse import urlsplit, unquote
from .models import AppError


def redact(text, secrets=()):
    text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)(https?|ssh)://[^\s/@]+@', r'\1://[REDACTED]@', text)
    text = re.sub(r'(?i)([?&](?:token|access_token|private_token|password|auth)=)[^\s&#]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:authorization|private-token)\s*[:=]\s*)(?:bearer\s+|token\s+)?[^\s]+', r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|glpat-[A-Za-z0-9_-]+)\b', '[REDACTED]', text)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    return ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)


def https_url(value):
    try:
        p = urlsplit(value)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment:
            raise ValueError()
        _ = p.port
        if any(ord(c) <= 32 for c in value) or '\\' in value:
            raise ValueError()
        return p
    except ValueError:
        raise AppError('url', 'Eine HTTPS-URL ohne Zugangsdaten oder Fragment ist erforderlich.') from None


@dataclass(frozen=True)
class Repository:
    clone: str
    provider: str
    host: str
    project: str
    web_origin: str
    api_origin: str

    @classmethod
    def parse(cls, value, provider, web_origin=''):
        if provider not in ('GitHub', 'GitLab'):
            raise AppError('provider', 'GitHub oder GitLab auswaehlen.')
        if not value or any(ord(c) <= 32 for c in value) or '\\' in value:
            raise AppError('url', 'Repository-URL ist ungueltig.')
        try:
            if value.startswith(('https://', 'ssh://')):
                p = urlsplit(value)
                if not p.hostname or p.password or p.query or p.fragment:
                    raise ValueError()
                if p.scheme == 'https' and p.username:
                    raise ValueError()
                if p.scheme == 'ssh' and p.username not in (None, 'git'):
                    raise ValueError()
                host, path = p.hostname.lower(), p.path.strip('/')
                default_origin = f'https://{p.netloc}' if p.scheme == 'https' else f'https://{host}'
                _ = p.port
            else:
                match = re.fullmatch(r'git@([A-Za-z0-9.-]+):(.+)', value)
                if not match:
                    raise ValueError()
                host, path = match.group(1).lower(), match.group(2).strip('/')
                default_origin = f'https://{host}'
            path = unquote(path)
            if path.endswith('.git'):
                path = path[:-4]
            parts = path.split('/')
            if len(parts) < 2 or any(not s or s in ('.', '..') or s.startswith('-') for s in parts):
                raise ValueError()
            if not re.fullmatch(r'[A-Za-z0-9_.\-/]+', path):
                raise ValueError()
            if provider == 'GitHub' and len(parts) != 2:
                raise ValueError()
            if (host == 'github.com' and provider != 'GitHub') or (host == 'gitlab.com' and provider != 'GitLab'):
                raise ValueError()
        except ValueError:
            raise AppError('url', 'HTTPS- oder SSH-Clone-URL ohne Token verwenden; Plattform und Projektpfad pruefen.') from None
        origin = web_origin.rstrip('/') or default_origin
        p = https_url(origin)
        if p.path or p.query:
            raise AppError('url', 'Web-Host muss eine HTTPS-Origin ohne Pfad sein.')
        if not web_origin and host == 'github.com':
            origin = 'https://github.com'
        if provider == 'GitHub':
            api = 'https://api.github.com' if origin == 'https://github.com' else origin + '/api/v3'
        else:
            api = origin + '/api/v4'
        return cls(value, provider, p.netloc.lower(), path, origin, api)
