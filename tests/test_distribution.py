"""Contratos verificáveis sem fingir ter gerado um executável Windows."""
from pathlib import Path
import sys
import pytest
import build
from nexus.core.database import default_path


def test_data_path_stays_outside_frozen_temp(monkeypatch, tmp_path):
    permanent = tmp_path / 'Dados de usuário São Paulo'
    extracted = tmp_path / '_MEI123'
    monkeypatch.setenv('LOCALAPPDATA', str(permanent))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(extracted), raising=False)
    assert default_path() == permanent / 'Nexus' / 'nexus.sqlite3'
    assert extracted not in default_path().parents


def test_standard_bundle_excludes_later_phases():
    command = build.command()
    assert command[-1] == 'main.py'
    assert '--onedir' in command
    assert '--exclude-module' in command
    assert 'nexus.ui.main_window' in command
    assert 'rawpy' not in [command[i+1] for i, value in enumerate(command[:-1]) if value == '--collect-all']


def test_build_dry_run_never_launches_process(monkeypatch, capsys):
    def prohibited(*args, **kwargs):
        raise AssertionError('Simulação não pode iniciar subprocessos')
    monkeypatch.setattr(build.subprocess, 'run', prohibited)
    assert build.main(['--dry-run']) == 0
    assert 'PyInstaller' in capsys.readouterr().out
    assert build.main(['--dry-run', '--experimental']) == 0
    assert '--collect-all rawpy' in capsys.readouterr().out


def test_build_rejects_cross_compiling(monkeypatch):
    monkeypatch.setattr(build.sys, 'platform', 'linux')
    with pytest.raises(SystemExit) as error:
        build.main([])
    assert error.value.code == 2


def test_default_app_imports_without_experimental_dependencies():
    import subprocess
    code = '''
import builtins
import sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'rawpy', 'pyqtgraph', 'numpy'}:
        raise ModuleNotFoundError('optional dependency deliberately unavailable')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from nexus.app import Window
assert 'nexus.ui.main_window' not in sys.modules
assert Window.__module__ == 'nexus.ui.foundation'
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
