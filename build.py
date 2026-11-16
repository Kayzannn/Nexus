"""Empacotamento explícito em Windows, sem download de código em execução."""
import argparse
import subprocess
import sys
from pathlib import Path


def command(experimental: bool = False) -> list[str]:
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
            '--name', 'NEXUS', '--collect-all', 'exifread']
    if experimental:
        args += ['--collect-all', 'pyqtgraph', '--collect-all', 'rawpy']
    else:
        for name in ['nexus.ui.main_window', 'nexus.ui.base', 'nexus.ui.dashboard', 'rawpy', 'pyqtgraph', 'numpy']:
            args += ['--exclude-module', name]
    return args + ['main.py']


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Mostra o comando sem executar')
    parser.add_argument('--experimental', action='store_true', help='Inclui as Fases 3–5; requer .[experimental]')
    args = parser.parse_args(argv)
    if args.dry_run:
        print(subprocess.list2cmdline(command(args.experimental)))
        return 0
    if sys.platform != 'win32':
        parser.error('Gere o executável Windows em Windows; use --dry-run para inspecionar o comando.')
    return subprocess.run(command(args.experimental), cwd=Path(__file__).resolve().parent, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
