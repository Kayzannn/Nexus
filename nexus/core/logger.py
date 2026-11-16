"""Logs locais rotativos e erros estruturados no SQLite, sem saída de scripts."""
import logging
from logging.handlers import RotatingFileHandler
import threading
import traceback

_lock = threading.Lock()


def get_logger(db):
    path = db.path.parent / 'logs' / 'nexus.log'
    with _lock:
        logger = logging.getLogger('nexus.' + str(db.path.resolve()))
        if not logger.handlers:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
        return logger


def log_error(db, context, error, details=None):
    details = details if details is not None else ''.join(traceback.format_exception(error))
    get_logger(db).error('%s: %s\n%s', context, error, details)
    try:
        db.execute('INSERT INTO error_logs(context,message,traceback) VALUES(?,?,?)', (context, str(error), details))
    except Exception:
        get_logger(db).exception('Não foi possível persistir o erro no SQLite')


def close_logger(db):
    """Libera os arquivos de log ao fechar a janela, inclusive no Windows."""
    with _lock:
        logger = logging.getLogger('nexus.' + str(db.path.resolve()))
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
