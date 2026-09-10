import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from threading import Event
from .models import AppError, Cancelled, Report, checkpoint
from .security import redact


class GitService:
    def __init__(self, project, cancel=None, log=None):
        if os.name == 'nt':
            import ctypes
            full = os.path.abspath(os.fspath(project))
            drive, tail = os.path.splitdrive(full)
            if drive.endswith(':'):
                try:
                    buffer = ctypes.create_unicode_buffer(32768)
                    size = ctypes.c_ulong(len(buffer))
                    if ctypes.windll.mpr.WNetGetConnectionW(drive, buffer, ctypes.byref(size)) == 0:
                        project = buffer.value.rstrip('\\/') + tail
                except (AttributeError, OSError):
                    pass
        self.project = Path(project).resolve()
        self.cancel = cancel or Event()
        self.log = log or (lambda text: None)
        self.executable = shutil.which('git')
        if not self.executable:
            raise AppError('git_missing', 'Git fehlt. Git for Windows installieren und die Anwendung neu starten.')

    def run(self, *args, allowed=(0,), timeout=180):
        checkpoint(self.cancel)
        env = os.environ.copy()
        # Do not allow inherited Git routing variables to redirect operations.
        for name in list(env):
            if name.startswith('GIT_') and name not in ('GIT_SSH', 'GIT_SSH_COMMAND', 'GIT_SSH_VARIANT', 'GIT_ASKPASS'):
                env.pop(name)
        env.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never', GIT_MERGE_AUTOEDIT='no', LC_ALL='C')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        command = [self.executable, '-c', 'color.ui=false', *map(str, args)]
        # Output goes to a temporary file: no pipe deadlock or unbounded RAM buffering.
        with tempfile.TemporaryFile() as output:
            try:
                proc = subprocess.Popen(command, cwd=self.project, env=env, stdin=subprocess.DEVNULL,
                                        stdout=output, stderr=subprocess.STDOUT, shell=False, creationflags=flags, start_new_session=os.name != 'nt')
                start = time.monotonic()
                while proc.poll() is None:
                    if self.cancel.is_set() or time.monotonic() - start > timeout:
                        if os.name == 'nt':
                            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           shell=False, creationflags=flags, timeout=10)
                        else:
                            import signal
                            try:
                                os.killpg(proc.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        if proc.poll() is None:
                            proc.kill()
                        proc.wait()
                        if self.cancel.is_set():
                            raise Cancelled()
                        raise AppError('git_timeout', 'Git-Zeitlimit erreicht. Remote-Stand vor einem erneuten Push pruefen.', True)
                    time.sleep(.04)
                output.seek(0)
                raw = output.read(2_000_000).decode('utf-8', 'replace').strip()
            except OSError:
                raise AppError('git_process', 'Git konnte nicht gestartet werden. Installation und Projektpfad pruefen.') from None
        if proc.returncode not in allowed:
            self.log(redact(raw))
            raise AppError('git_failed', redact(raw) or f'Git meldet Fehler {proc.returncode}.')
        if raw:
            self.log(redact(raw))
        return proc.returncode, raw

    def valid_ref(self, value, kind='heads'):
        if not value or value.startswith('-') or value == 'HEAD' or value.startswith('@{-'):
            raise AppError('ref', 'Branch oder Tag ist ungueltig.')
        code, _ = self.run('check-ref-format', f'refs/{kind}/{value}', allowed=(0, 1))
        if code:
            raise AppError('ref', 'Git lehnt den Branch- oder Tag-Namen ab.')

    def ensure_project(self, branch='main'):
        if not self.project.is_dir():
            raise AppError('project', 'Einen vorhandenen Projektordner auswaehlen.')
        if not (self.project / '.git').exists():
            code, _ = self.run('rev-parse', '--show-toplevel', allowed=(0, 128))
            if code == 0:
                raise AppError('nested', 'Der Ordner liegt in einem anderen Repository. Dessen Projektwurzel auswaehlen.')
            self.valid_ref(branch)
            self.run('init', '--initial-branch', branch)
        _, root = self.run('rev-parse', '--show-toplevel')
        if Path(root).resolve() != self.project:
            raise AppError('root', 'Bitte die Wurzel des Git-Arbeitsverzeichnisses auswaehlen.')
        for marker in ('MERGE_HEAD', 'rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD', 'REVERT_HEAD'):
            _, raw = self.run('rev-parse', '--git-path', marker)
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = self.project / candidate
            if candidate.exists():
                raise AppError('operation_pending', 'Zuerst den laufenden Merge, Rebase oder Cherry-Pick in Git abschliessen.')

    def review(self, branch):
        self.ensure_project(branch)
        self.valid_ref(branch)
        _, status = self.run('status', '--short', '--untracked-files=all')
        _, tracked = self.run('diff', '--stat', 'HEAD', allowed=(0, 128))
        return redact(status or 'Keine lokalen Aenderungen.') + '\n\n' + redact(tracked)

    def remote_refs(self, remote, ref):
        _, text = self.run('ls-remote', remote, ref, ref + '^{}')
        refs = {}
        for line in text.splitlines():
            parts = line.split('\t', 1)
            if len(parts) == 2 and parts[1] in (ref, ref + '^{}'):
                refs[parts[1]] = parts[0]
        return refs

    def check_connection(self, remote):
        self.run('ls-remote', '--heads', remote)
        return 'Repository lesbar. Das bestaetigt noch keine Push- oder API-Berechtigung.'

    def verify_tag(self, remote, tag, expected):
        self.valid_ref(tag, 'tags')
        ref = f'refs/tags/{tag}'
        refs = self.remote_refs(remote, ref)
        if refs.get(ref + '^{}', refs.get(ref)) != expected:
            raise AppError('tag_mismatch', 'Remote-Tag fehlt oder verweist nicht auf den erfolgreich gepushten Commit.')

    def push_tag(self, remote, tag, message, expected):
        self.valid_ref(tag, 'tags')
        ref = f'refs/tags/{tag}'
        refs = self.remote_refs(remote, ref)
        if ref in refs:
            self.verify_tag(remote, tag, expected)
            return 'Remote-Tag ist bereits korrekt vorhanden.'
        code, local = self.run('rev-parse', '--verify', ref + '^{commit}', allowed=(0, 128))
        if code == 0:
            if local != expected:
                raise AppError('tag_mismatch', 'Lokaler Tag zeigt auf einen anderen Commit; er wird nicht ersetzt.')
        else:
            args = ['tag', '-a', tag, '-m', message, expected] if message else ['tag', tag, expected]
            self.run(*args)
        self.run('push', remote, f'{ref}:{ref}', timeout=600)
        self.verify_tag(remote, tag, expected)
        return 'Tag gepusht und Remote-Ziel geprueft.'

    def push(self, options):
        report = Report()
        stage = 'Vorbereitung'
        try:
            if options.mode not in ('safe', 'replace', 'integrate'):
                raise AppError('mode', 'Unbekannter Konfliktmodus.')
            if not options.message.strip():
                raise AppError('message', 'Commit-Nachricht fehlt.')
            self.valid_ref(options.branch)
            if options.tag:
                self.valid_ref(options.tag, 'tags')
            self.ensure_project(options.branch)
            _, current = self.run('symbolic-ref', '--quiet', '--short', 'HEAD', allowed=(0, 1))
            if current != options.branch:
                code, _ = self.run('show-ref', '--verify', '--quiet', f'refs/heads/{options.branch}', allowed=(0, 1))
                if code == 0:
                    raise AppError('branch_exists', 'Ziel-Branch existiert lokal bereits. Zuerst bewusst in Git auf diesen Branch wechseln; kein automatisches Zuruecksetzen.')
                if not current:
                    raise AppError('detached', 'Detached HEAD: zuerst in Git einen lokalen Branch auschecken.')
                self.run('switch', '-c', options.branch)
            ref = f'refs/heads/{options.branch}'
            observed = self.remote_refs(options.remote, ref).get(ref)
            if observed:
                self.run('fetch', '--no-tags', options.remote, ref)
                _, fetched = self.run('rev-parse', 'FETCH_HEAD')
                if fetched != observed:
                    raise AppError('remote_changed', 'Remote hat sich waehrend der Pruefung geaendert. Erneut pruefen.', True)
            stage = 'Commit'
            self.run('add', '-A', '--', '.')
            code, _ = self.run('diff', '--cached', '--quiet', allowed=(0, 1))
            if code:
                self.run('commit', '-m', options.message, timeout=600)
                report.add(stage, 'success', 'Lokale Aenderungen committed.')
            else:
                report.add(stage, 'skipped', 'Keine neuen Aenderungen; vorhandener Commit wird verwendet.')
            _, commit = self.run('rev-parse', '--verify', 'HEAD^{commit}')
            stage = 'Branch-Push'
            divergent = False
            if observed:
                code, _ = self.run('merge-base', '--is-ancestor', observed, commit, allowed=(0, 1))
                divergent = code == 1
            if divergent and options.mode == 'safe':
                raise AppError('divergence', 'Remote enthaelt zusaetzliche Commits. Sicher abgebrochen; lokaler Commit bleibt erhalten.')
            if divergent and options.mode == 'integrate':
                args = ['merge', '--no-edit']
                if options.allow_unrelated:
                    args.append('--allow-unrelated-histories')
                self.run(*args, observed)
                # On conflict leave the merge in place, so the user can resolve it.
                _, commit = self.run('rev-parse', 'HEAD')
            args = ['push']
            if options.mode == 'replace':
                # Explicit empty expected value also protects a previously absent branch.
                args.append(f'--force-with-lease={ref}:{observed or ""}')
            args.extend([options.remote, f'{commit}:{ref}'])
            self.run(*args, timeout=600)
            report.commit = commit
            report.add(stage, 'success', 'Branch gepusht. Bestehende Remote-Konfiguration unveraendert.')
            if options.tag:
                stage = 'Tag-Push'
                detail = self.push_tag(options.remote, options.tag, options.tag_message, commit)
                report.tag = options.tag
                report.add(stage, 'success', detail)
            else:
                report.add('Tag-Push', 'skipped', 'Kein Tag angefordert.')
        except AppError as error:
            report.add(stage, 'cancelled' if isinstance(error, Cancelled) else 'failed', str(error), code=error.code)
            if stage != 'Tag-Push' and options.tag:
                report.add('Tag-Push', 'blocked', 'Wegen des vorherigen Fehlers nicht ausgefuehrt.')
        return report
