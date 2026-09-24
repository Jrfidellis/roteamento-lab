"""Formato do arquivo de configuração de cada roteador: configs/proprio/<no>.json.

Os parâmetros de tempo existem para que a comparação com OSPF e RIP seja feita
com valores explícitos e documentados. Campos novos podem ser acrescentados em
"parametros" sem alterar esta classe.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    no: str                             # nome do roteador: "a" ... "e"
    router_id: str                      # ex.: "1.1.1.1"
    intervalo_hello_s: float            # período de envio de hello aos vizinhos
    tempo_morto_s: float                # sem mensagens por este tempo, o vizinho é dado como caído
    intervalo_anuncio_s: float          # período de envio dos anúncios de rota
    parametros: dict[str, Any] = field(default_factory=dict)  # livres para o algoritmo

    @classmethod
    def carregar(cls, caminho: str | Path) -> "Config":
        """Lê e valida o JSON. Única função concreta do pacote: é o contrato do arquivo."""
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        obrigatorios = {"no", "router_id", "intervalo_hello_s", "tempo_morto_s", "intervalo_anuncio_s"}
        faltando = obrigatorios - dados.keys()
        if faltando:
            raise ValueError(f"{caminho}: campos obrigatórios ausentes: {sorted(faltando)}")
        return cls(**dados)
