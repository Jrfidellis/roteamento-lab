"""Estruturas de dados compartilhadas pelos componentes do algoritmo.

São apenas descrições de dados, sem comportamento. Campos podem ser acrescentados;
os existentes são usados pelas interfaces e não devem ser removidos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from typing import Any


@dataclass(frozen=True)
class Interface:
    """Interface de rede do roteador que participa do algoritmo."""

    nome: str                 # nome no kernel, ex.: "eth1"
    endereco: IPv4Interface   # endereço com máscara, ex.: 10.0.10.1/24

    @property
    def rede(self) -> IPv4Network:
        return self.endereco.network


@dataclass
class Vizinho:
    """Roteador adjacente descoberto em uma das interfaces."""

    router_id: str            # identificador do vizinho, ex.: "2.2.2.2"
    endereco: IPv4Address     # endereço do vizinho na rede compartilhada (próximo salto)
    interface: Interface      # interface local por onde o vizinho é alcançado
    visto_em: float           # time.monotonic() da última mensagem recebida dele
    custo: float = 0.0        # custo do enlace até o vizinho, definido por Metrica


@dataclass(frozen=True)
class Rota:
    """Rota calculada pelo algoritmo, pronta para ir ao kernel."""

    destino: IPv4Network                 # prefixo de destino
    proximo_salto: IPv4Address | None    # None para rede diretamente conectada
    interface: str                       # nome da interface de saída
    metrica: float                       # custo total segundo o critério da dupla


@dataclass
class Mensagem:
    """Mensagem de controle trocada entre roteadores pela PORTA_UDP.

    O formato do corpo e os tipos existentes são decisão da dupla
    (ex.: "hello", "anuncio"). O codec é definido em interfaces.Codec.
    """

    tipo: str                      # tipo da mensagem
    origem: str                    # router_id de quem enviou
    sequencia: int                 # número de sequência do emissor
    corpo: dict[str, Any] = field(default_factory=dict)
