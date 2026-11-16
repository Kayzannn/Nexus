"""Análise, planos imutáveis, histórico por arquivo e desfazer conservador."""
import os
import errno
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, TypedDict
from PIL import Image
from nexus.services.files import digest
from nexus.core.logger import get_logger, log_error

RAW = {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2'}


class FileRow(TypedDict):
    path: str
    name: str
    extension: str
    size: int
    created: float | None
    modified: float
    captured: float | None


def capture_date(path: Path) -> float | None:
    if path.suffix.lower() not in RAW | {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp'}:
        return None
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            value = exif.get(36867) or exif.get_ifd(34665).get(36867)
            if value:
                return datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S').timestamp()
    except (OSError, ValueError, TypeError, KeyError):
        pass
    if path.suffix.lower() in RAW:
        try:
            import exifread
            with path.open('rb') as stream:
                tags = exifread.process_file(stream, details=False)
            value = tags.get('EXIF DateTimeOriginal')
            if value:
                return datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S').timestamp()
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return None


def scan(folder: str | Path, recursive: bool = False, on_error: Callable | None = None) -> list[FileRow]:
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError('Selecione uma pasta existente.')
    rows = []
    def report(path, exc):
        if on_error is None:
            raise exc
        on_error(path, exc)

    pending = [folder]
    while pending:
        directory = pending.pop()
        try:
            paths = sorted(directory.iterdir())
        except OSError as exc:
            report(directory, exc)
            continue
        subdirectories = []
        for path in paths:
            try:
                if path.is_symlink() or path.is_junction():
                    continue
                if path.is_dir():
                    if recursive:
                        subdirectories.append(path)
                elif path.is_file():
                    stat = path.stat()
                    birth = getattr(stat, 'st_birthtime', stat.st_ctime if os.name == 'nt' else None)
                    rows.append(dict(path=str(path), name=path.name, extension=path.suffix.lower(), size=stat.st_size,
                                     created=birth, modified=stat.st_mtime, captured=capture_date(path)))
            except (OSError, ValueError) as exc:
                report(path, exc)
        pending.extend(reversed(subdirectories))
    return rows


def filter_rows(rows, extension='', minimum=0, maximum=None, after=None, before=None, date_key='modified'):
    extensions = {s.strip().lower() for s in extension.split(',') if s.strip()}
    return [r for r in rows if (not extensions or r['extension'] in extensions)
            and r['size'] >= minimum and (maximum is None or r['size'] <= maximum)
            and (after is None or (r[date_key] is not None and r[date_key] >= after))
            and (before is None or (r[date_key] is not None and r[date_key] <= before))]


def valid_name(name: str) -> str:
    if not name or name.endswith((' ', '.')) or any(c in name for c in '<>:"/\\|?*') or any(ord(c) < 32 for c in name):
        raise ValueError('Nome inválido para Windows.')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError('Nome reservado pelo Windows.')
    return name


@dataclass(frozen=True)
class Change:
    source: Path
    target: Path
    digest: str


def validate_plan(plan):
    targets = set()
    for change in plan:
        key = str(change.target).casefold()
        if key in targets:
            raise FileExistsError('Dois arquivos receberiam o mesmo nome.')
        targets.add(key)
        if change.target.exists() or change.target.is_symlink():
            raise FileExistsError(f'Destino já existe: {change.target}')
    return plan


def rename_plan(rows: list[FileRow], base: str = 'Foto', prefix: str = '', suffix: str = '', order: str = 'captured', reverse: bool = False, fallback: str = 'modified') -> list[Change]:
    for part in (base, prefix, suffix):
        if part:
            valid_name(part)
    if order not in {'name', 'extension', 'size', 'captured', 'created', 'modified'} or fallback not in {'created', 'modified'}:
        raise ValueError('Ordenação inválida.')
    def key(row):
        value = row[order]
        if value is None:
            value = row[fallback]
        if value is None:
            raise ValueError('Data de criação indisponível; escolha modificação como alternativa.')
        return value, row['path']
    result = []
    for index, row in enumerate(sorted(rows, key=key, reverse=reverse), 1):
        source = Path(row['path'])
        name = valid_name(f'{prefix}{base}_{index:03d}{suffix}{source.suffix}')
        target = source.with_name(name)
        if target != source:
            result.append(Change(source, target, digest(source)))
    return validate_plan(result)


CATEGORIES = {'.jpg': 'Imagens', '.png': 'Imagens', '.jpeg': 'Imagens', '.pdf': 'Documentos', '.txt': 'Documentos',
              '.py': 'Codigo', '.stl': 'Impressao3D', '.3mf': 'Impressao3D', **{ext: 'RAW' for ext in RAW}}


def category_plan(rows: list[FileRow], destination: str | Path) -> list[Change]:
    destination = Path(destination).resolve()
    plan = []
    for row in rows:
        source = Path(row['path'])
        target = destination / CATEGORIES.get(source.suffix.lower(), 'Outros') / source.name
        if source != target:
            plan.append(Change(source, target, digest(source)))
    return validate_plan(plan)


def move_exclusive(source: Path, target: Path) -> None:
    """Move without replacement, including across volumes."""
    try:
        if os.name == 'nt':
            os.rename(source, target)
        else:
            os.link(source, target, follow_symlinks=False)
            try:
                source.unlink()
            except BaseException:
                target.unlink()
                raise
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, 'winerror', None) != 17:
            raise
    expected = digest(source)
    created = False
    try:
        with source.open('rb') as src, target.open('xb') as dst:
            created = True
            shutil.copyfileobj(src, dst)
        if digest(target) != expected or digest(source) != expected:
            raise ValueError('Origem alterada durante a movimentação.')
        shutil.copystat(source, target)
        source.unlink()
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise


@dataclass
class BatchResult:
    completed: int = 0
    failed: int = 0
    simulated: int = 0
    errors: list[str] = field(default_factory=list)
    previews: list[str] = field(default_factory=list)

    def __str__(self):
        return f'{self.completed} concluído(s), {self.failed} falha(s), {self.simulated} simulado(s)'


def independent_plan(plan):
    sources = [str(p.source.resolve()).casefold() for p in plan]
    targets = [str(p.target.resolve()).casefold() for p in plan]
    if len(set(sources)) != len(sources) or len(set(targets)) != len(targets):
        raise ValueError('O lote contém origens ou destinos repetidos.')
    if set(sources) & set(targets):
        raise ValueError('O lote contém operações dependentes; separe os lotes.')


class FileManager:
    def __init__(self, db):
        self.db = db

    def execute(self, plan, kind='rename', *, dry_run=False, continue_on_error=False):
        if kind not in {'rename', 'move'}:
            raise ValueError('Tipo de operação inválido.')
        return self._batch(plan, kind, dry_run, continue_on_error)

    def _batch(self, plan, kind, dry_run, continue_on_error):
        from nexus.services.files import execute_copy
        plan = list(plan)
        independent_plan(plan)
        if not continue_on_error:
            validate_plan(plan)
        result = BatchResult()
        batch = None
        if not dry_run:
            batch = self.db.execute('INSERT INTO operation_batches(kind,status) VALUES(?,?)', (kind, 'running'))
            get_logger(self.db).info('Lote %s iniciado: %s, %s itens', batch, kind, len(plan))
        for item in plan:
            operation = None
            changed = False
            if not dry_run:
                operation = self.db.execute('INSERT INTO file_operations(kind,source,target,digest,status,batch_id) VALUES(?,?,?,?,?,?)',
                    (kind, str(item.source), str(item.target), item.digest, 'pending', batch))
            try:
                validate_plan([item])
                if item.source.is_symlink() or digest(item.source) != item.digest:
                    raise ValueError('Origem alterada após a prévia.')
                if kind != 'copy':
                    self.check_references(str(item.source), str(item.target))
                if dry_run:
                    result.simulated += 1
                    result.previews.append(f'{item.source} → {item.target}')
                    continue
                if kind == 'copy':
                    execute_copy([item])
                else:
                    item.target.parent.mkdir(parents=True, exist_ok=True)
                    move_exclusive(item.source, item.target)
                changed = True
                if kind != 'copy':
                    self.relocate_references(str(item.source), str(item.target))
                self.db.execute('UPDATE file_operations SET status=? WHERE id=?', ('done', operation))
                result.completed += 1
                get_logger(self.db).info('Operação %s concluída: %s -> %s', operation, item.source, item.target)
            except Exception as exc:
                result.failed += 1
                result.errors.append(f'{item.source}: {exc}')
                if not dry_run:
                    log_error(self.db, f'file_operation:{operation}', exc)
                    self.db.execute('UPDATE file_operations SET status=?,error=? WHERE id=?',
                        ('needs_recovery' if changed else 'failed', str(exc), operation))
                # A filesystem change followed by a persistence failure is ambiguous:
                # halt even in best-effort mode so recovery can inspect the journal.
                if changed or not continue_on_error:
                    if batch:
                        self.db.execute("UPDATE operation_batches SET status='failed',finished=CURRENT_TIMESTAMP WHERE id=?", (batch,))
                    raise RuntimeError(f'{result}. Falha em {item.source}: {exc}') from exc
        if batch:
            self.db.execute('UPDATE operation_batches SET status=?,finished=CURRENT_TIMESTAMP WHERE id=?',
                            ('partial' if result.failed and result.completed else 'failed' if result.failed else 'done', batch))
            get_logger(self.db).info('Lote %s finalizado: %s', batch, result)
        return result if dry_run or continue_on_error else result.completed

    def undo(self, record):
        current = self.db.rows('SELECT * FROM file_operations WHERE id=?', (record['id'],))
        if not current or current[0]['status'] != 'done' or current[0]['kind'] not in {'rename', 'move'}:
            raise ValueError('A operação não pode ser desfeita.')
        record = current[0]
        source, target = Path(record['source']), Path(record['target'])
        if target.is_symlink() or digest(target) != record['digest']:
            raise ValueError('O destino foi alterado; desfazer foi bloqueado.')
        validate_plan([Change(target, source, record['digest'])])
        self.check_references(str(target), str(source))
        self.db.execute('UPDATE file_operations SET status=? WHERE id=?', ('undo_pending', record['id']))
        try:
            move_exclusive(target, source)
            self.relocate_references(str(target), str(source))
            self.db.execute('UPDATE file_operations SET status=? WHERE id=?', ('undone', record['id']))
            get_logger(self.db).info('Operação %s desfeita', record['id'])
        except Exception as exc:
            log_error(self.db, f"undo:{record['id']}", exc)
            raise
        return 1

    def duplicates(self, rows: list[FileRow]) -> list[list[str]]:
        by_size: dict[int, list[Path]] = {}
        for row in rows:
            path = Path(row['path'])
            if path.is_symlink():
                continue
            by_size.setdefault(path.stat().st_size, []).append(path)
        groups: list[list[str]] = []
        for candidates in by_size.values():
            if len(candidates) < 2:
                continue
            by_hash: dict[str, list[str]] = {}
            for path in candidates:
                by_hash.setdefault(digest(path), []).append(str(path))
            groups.extend(paths for paths in by_hash.values() if len(paths) > 1)
        return groups

    def check_references(self, source, target):
        old = self.db.rows('SELECT id FROM photos WHERE path=?', (source,))
        new = self.db.rows('SELECT id FROM photos WHERE path=?', (target,))
        if old and new and old[0]['id'] != new[0]['id']:
            raise ValueError('O destino já tem uma referência no catálogo de fotos. Resolva o conflito no catálogo primeiro.')

    def relocate_references(self, source, target):
        with self.db.connect() as conn:
            old = conn.execute('SELECT id FROM photos WHERE path=?', (source,)).fetchone()
            new = conn.execute('SELECT id FROM photos WHERE path=?', (target,)).fetchone()
            if old and new and old['id'] != new['id']:
                raise ValueError('O destino já tem uma referência no catálogo de fotos.')
            conn.execute('UPDATE photos SET path=? WHERE path=?', (target, source))
            conn.execute('UPDATE materials SET path=? WHERE path=?', (target, source))
            conn.execute('UPDATE profiles SET image=? WHERE image=?', (target, source))
            conn.execute('UPDATE scripts SET path=? WHERE path=?', (target, source))

    def copy(self, plan, *, dry_run=False, continue_on_error=False):
        return self._batch(plan, 'copy', dry_run, continue_on_error)

    def recover(self):
        """Reconcile journal metadata only; never delete, move or overwrite files."""
        rows = self.db.rows("SELECT * FROM file_operations WHERE status IN ('pending','needs_recovery','undo_pending')")
        result = BatchResult()
        for row in rows:
            source, target = Path(row['source']), Path(row['target'])
            try:
                source_ok = source.is_file() and not source.is_symlink() and digest(source) == row['digest']
                target_ok = target.is_file() and not target.is_symlink() and digest(target) == row['digest']
                if row['status'] == 'undo_pending':
                    if source_ok and not target.exists():
                        self.relocate_references(str(target), str(source))
                        status = 'undone'
                    elif target_ok and not source.exists():
                        status = 'done'
                    else:
                        raise ValueError('Desfazer ambíguo; verifique os dois caminhos manualmente.')
                elif row['kind'] == 'copy' and target_ok:
                    status = 'done'
                elif row['kind'] in {'rename', 'move'} and target_ok and not source.exists():
                    self.relocate_references(str(source), str(target))
                    status = 'done'
                elif source_ok and not target.exists():
                    status = 'failed'
                else:
                    raise ValueError('Estado ambíguo; nenhum arquivo será alterado ou removido.')
                self.db.execute('UPDATE file_operations SET status=?,error=? WHERE id=?', (status, 'Estado conciliado por inspeção de hashes.', row['id']))
                get_logger(self.db).info('Operação %s recuperada como %s', row['id'], status)
                result.completed += 1
            except Exception as exc:
                result.failed += 1
                result.errors.append(f"#{row['id']}: {exc}")
                log_error(self.db, f"recovery:{row['id']}", exc)
        for batch in {row['batch_id'] for row in rows if row['batch_id'] is not None}:
            states = [r['status'] for r in self.db.rows('SELECT status FROM file_operations WHERE batch_id=?', (batch,))]
            status = 'needs_recovery' if any(s in {'pending', 'needs_recovery', 'undo_pending'} for s in states) else 'recovered'
            self.db.execute('UPDATE operation_batches SET status=?,finished=CURRENT_TIMESTAMP WHERE id=?', (status, batch))
        return result
