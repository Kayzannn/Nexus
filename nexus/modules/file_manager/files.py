"""Cópias sem sobrescrita e identificação de arquivos por SHA-256."""
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


@dataclass(frozen=True)
class CopyItem:
    source: Path
    target: Path
    digest: str


def plan_copy(source: Path, destination: Path, extension="") -> list[CopyItem]:
    source, destination = source.resolve(), destination.resolve()
    if not source.is_dir():
        raise ValueError("A origem deve ser uma pasta existente.")
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError("Origem e destino não podem ser pastas sobrepostas.")
    if destination.exists() and not destination.is_dir():
        raise ValueError("O destino deve ser uma pasta.")
    extension = extension.strip().lower()
    if extension and (not extension.startswith(".") or any(c in extension for c in "*/\\?")):
        raise ValueError("Use uma extensão como .jpg ou deixe em branco.")
    result = []
    for path in sorted(source.iterdir()):
        if path.is_file() and not path.is_symlink() and (not extension or path.suffix.lower() == extension):
            target = destination / path.name
            if target.exists() or target.is_symlink():
                raise FileExistsError(f"O destino já existe: {target.name}")
            result.append(CopyItem(path, target, digest(path)))
    return result


def execute_copy(items: list[CopyItem]) -> int:
    for item in items:
        if item.source.is_symlink() or digest(item.source) != item.digest:
            raise ValueError(f"Arquivo alterado após a prévia: {item.source.name}")
        item.target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects even when another process creates a file after preview.
        created = False
        try:
            with item.source.open("rb") as src, item.target.open("xb") as dst:
                created = True
                shutil.copyfileobj(src, dst)
            if digest(item.target) != item.digest:
                raise ValueError(f"Conteúdo alterado durante a cópia: {item.source.name}")
        except BaseException:
            # Close handles before unlinking, including on Windows.
            if created:
                item.target.unlink(missing_ok=True)
            raise
    return len(items)


def duplicates(folder: Path) -> list[list[str]]:
    groups = {}
    for path in sorted(folder.iterdir()):
        if path.is_file() and not path.is_symlink():
            groups.setdefault((path.stat().st_size, digest(path)), []).append(str(path))
    return [paths for paths in groups.values() if len(paths) > 1]
