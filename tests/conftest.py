"""Qt headless em CI Linux; não muda a configuração da aplicação instalada."""
import os
import sys

if sys.platform != 'win32' and not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
