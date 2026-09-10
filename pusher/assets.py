import hashlib
import os
import re
import tempfile
import zipfile
from pathlib import Path
from .models import AppError, Cancelled, Report, checkpoint


def sha256(path, cancel):
    result = hashlib.sha256()
    with Path(path).open('rb') as file:
        while True:
            checkpoint(cancel)
            block = file.read(1024 * 1024)
            if not block:
                return result.hexdigest()
            result.update(block)


def validate_files(paths):
    names = set()
    output = []
    for value in paths:
        path = Path(value)
        if path.is_symlink() or not path.is_file():
            raise AppError('asset_path', 'Nur regulaere Dateien ohne symbolische Links anhaengen.')
        # GitHub normalizes names; fail early instead of hiding remote collisions.
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', path.name) or path.name.endswith('.'):
            raise AppError('asset_name', 'Asset-Dateinamen muessen mit Buchstabe/Zahl beginnen und duerfen nur A-Z, a-z, 0-9, Punkt, Bindestrich und Unterstrich enthalten.')
        if path.name.casefold() in names:
            raise AppError('duplicate', 'Doppelte Dateinamen erkannt; vor Upload eindeutig umbenennen.')
        names.add(path.name.casefold())
        output.append(path.resolve())
    return output


def prepare(paths, output, make_zip, checksums, cancel):
    paths = validate_files(paths)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    names = {p.name.casefold() for p in paths}
    if (make_zip and 'release-bundle.zip' in names) or (checksums and 'sha256sums.txt' in names):
        raise AppError('duplicate', 'Generierte Dateinamen release-bundle.zip / SHA256SUMS.txt sind bereits belegt.')
    if make_zip:
        archive = output / 'release-bundle.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as target:
            for path in paths:
                checkpoint(cancel)
                info = zipfile.ZipInfo(path.name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                with path.open('rb') as source, target.open(info, 'w', force_zip64=True) as dest:
                    while True:
                        checkpoint(cancel)
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        dest.write(block)
        paths.append(archive)
    if checksums:
        manifest = output / 'SHA256SUMS.txt'
        manifest.write_text(''.join(f'{sha256(p, cancel)}  {p.name}\n' for p in paths), encoding='utf-8')
        paths.append(manifest)
    return paths


def upload_files(provider, release, paths, cancel, progress, status=None):
    status = status or (lambda text: None)
    report = Report()
    paths = validate_files(paths)
    for i, path in enumerate(paths):
        if cancel.is_set():
            report.add(path.name, 'cancelled', 'Nicht hochgeladen; Abbruch angefordert.', code='cancelled')
            status(path.name + '\tAbgebrochen')
            continue
        status(path.name + '\tWird geprueft / hochgeladen')
        try:
            # Snapshot prevents an application changing an EXE during hashing/upload.
            with tempfile.TemporaryDirectory(prefix='pusher-asset-') as folder:
                snapshot = Path(folder) / path.name
                with path.open('rb') as source, snapshot.open('xb') as dest:
                    while True:
                        checkpoint(cancel)
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        dest.write(block)
                digest = sha256(snapshot, cancel)
                asset, detail = provider.upload(release, snapshot, digest, cancel,
                                                 lambda sent, total: progress(path.name, sent, total))
                report.add(path.name, 'success', detail, asset.url)
        except Cancelled as error:
            report.add(path.name, 'cancelled', str(error), code=error.code)
        except AppError as error:
            report.add(path.name, 'failed', str(error), code=error.code)
        except OSError:
            report.add(path.name, 'failed', 'Datei konnte nicht gelesen oder zwischengespeichert werden. Freien Speicher und Rechte pruefen.', code='file_io')
        step = report.steps[-1]
        status(path.name + '\t' + {'success': 'Erfolgreich', 'failed': 'Fehler', 'cancelled': 'Abgebrochen'}[step.status])
    return report
