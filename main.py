"""Inicializa o NEXUS sem privilégios elevados."""
from nexus.app import main

if __name__ == '__main__':
    raise SystemExit(main())
