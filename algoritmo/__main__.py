"""Ponto de entrada: python3 -m algoritmo --config /config/proprio/<no>.json

Chamado pelo docker/router-entrypoint.sh quando PROTO=proprio.
"""

from __future__ import annotations

import argparse
import signal
import sys

from .config import Config
from .interfaces import criar_agente


def main() -> int:
    parser = argparse.ArgumentParser(prog="algoritmo")
    parser.add_argument("--config", required=True, help="configs/proprio/<no>.json")
    args = parser.parse_args()

    config = Config.carregar(args.config)
    try:
        agente = criar_agente(config)
    except NotImplementedError as erro:
        print(f"[{config.no}] {erro}", file=sys.stderr)
        return 2

    signal.signal(signal.SIGTERM, lambda *_: agente.parar())
    agente.executar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
