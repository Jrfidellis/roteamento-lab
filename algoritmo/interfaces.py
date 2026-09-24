"""Interfaces que o algoritmo próprio precisa implementar.

Cada classe abaixo é um componente com responsabilidade única. O Agente orquestra os
demais. Todos os métodos estão sem implementação (NotImplementedError); a dupla cria
classes concretas que herdam destas e as liga em criar_agente().

Fluxo esperado de um ciclo do Agente:
    1. Transporte.receber()        recebe mensagens dos vizinhos
    2. Vizinhanca.processar()      atualiza quem está vivo e o custo de cada enlace (via Metrica)
    3. CalculoRotas.processar()    incorpora os anúncios recebidos
    4. Vizinhanca.expirar()        remove vizinhos silenciosos há mais de tempo_morto_s
    5. CalculoRotas.calcular()     produz a tabela de rotas desejada
    6. TabelaKernel.sincronizar()  aplica a diferença no kernel
    7. Transporte.enviar()         envia hello e anúncios nos intervalos configurados
    8. RegistroEventos.registrar() em cada mudança relevante
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from ipaddress import IPv4Address

from .config import Config
from .tipos import Interface, Mensagem, Rota, Vizinho


class Codec(ABC):
    """Converte Mensagem para bytes e de volta. O formato de fio é decisão da dupla."""

    @abstractmethod
    def codificar(self, mensagem: Mensagem) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def decodificar(self, dados: bytes) -> Mensagem:
        """Deve levantar ValueError para dados malformados, nunca devolver lixo."""
        raise NotImplementedError


class Transporte(ABC):
    """Envio e recepção de mensagens de controle.

    Obrigatório: usar UDP na porta constantes.PORTA_UDP, em envio e recepção, para que o
    tráfego de controle seja medido. Unicast, broadcast ou multicast é decisão da dupla.
    """

    @abstractmethod
    def abrir(self, interfaces: list[Interface]) -> None:
        raise NotImplementedError

    @abstractmethod
    def enviar(self, mensagem: Mensagem, interface: Interface,
               destino: IPv4Address | None = None) -> None:
        """Envia pela interface. destino=None significa todos os vizinhos daquela rede."""
        raise NotImplementedError

    @abstractmethod
    def receber(self, timeout_s: float) -> list[tuple[Mensagem, IPv4Address, Interface]]:
        """Devolve as mensagens chegadas em até timeout_s, com remetente e interface de entrada."""
        raise NotImplementedError

    @abstractmethod
    def fechar(self) -> None:
        raise NotImplementedError


class Metrica(ABC):
    """Critério de custo de um enlace. É aqui que o algoritmo da dupla se diferencia
    do RIP (saltos) e do OSPF (custo por largura de banda)."""

    @abstractmethod
    def custo(self, vizinho: Vizinho) -> float:
        """Custo de alcançar o vizinho diretamente. Deve ser >= 0 e finito para vizinho vivo."""
        raise NotImplementedError


class Vizinhanca(ABC):
    """Descoberta e manutenção dos vizinhos."""

    @abstractmethod
    def processar(self, mensagem: Mensagem, remetente: IPv4Address, interface: Interface) -> None:
        raise NotImplementedError

    @abstractmethod
    def vizinhos(self) -> list[Vizinho]:
        """Vizinhos vivos no momento, já com custo atualizado."""
        raise NotImplementedError

    @abstractmethod
    def expirar(self, agora: float) -> list[Vizinho]:
        """Remove e devolve os vizinhos sem mensagens há mais de tempo_morto_s."""
        raise NotImplementedError


class CalculoRotas(ABC):
    """Seleção de rotas. Deve garantir ausência de loops em regime e após falhas."""

    @abstractmethod
    def processar(self, mensagem: Mensagem, vizinho: Vizinho) -> bool:
        """Incorpora um anúncio recebido. Devolve True se algo mudou."""
        raise NotImplementedError

    @abstractmethod
    def vizinho_caiu(self, vizinho: Vizinho) -> None:
        raise NotImplementedError

    @abstractmethod
    def calcular(self, vizinhos: list[Vizinho], conectadas: list[Interface]) -> list[Rota]:
        """Tabela completa desejada: uma rota por destino conhecido, conectadas incluídas."""
        raise NotImplementedError

    @abstractmethod
    def anuncio(self, interface: Interface) -> Mensagem:
        """Mensagem a anunciar nesta interface (split horizon, poison reverse etc. ficam aqui)."""
        raise NotImplementedError


class TabelaKernel(ABC):
    """Aplica a tabela calculada no kernel do roteador.

    Obrigatório: instalar e remover somente rotas com proto constantes.PROTO_KERNEL
    (ip route replace <destino> via <salto> dev <if> proto 99 metric <n>) e nunca mexer
    em rotas de outros protocolos nem nas rotas conectadas (proto kernel).
    """

    @abstractmethod
    def sincronizar(self, rotas: list[Rota]) -> tuple[list[Rota], list[Rota]]:
        """Deixa o kernel igual a `rotas` (ignorando as conectadas). Devolve (instaladas, removidas)."""
        raise NotImplementedError

    @abstractmethod
    def listar(self) -> list[Rota]:
        """Rotas com proto PROTO_KERNEL presentes no kernel agora."""
        raise NotImplementedError

    @abstractmethod
    def limpar(self) -> None:
        """Remove todas as rotas com proto PROTO_KERNEL. Chamado ao encerrar."""
        raise NotImplementedError


class RegistroEventos(ABC):
    """Log de eventos em JSON Lines: DIR_LOG/<no>.jsonl, um objeto por linha.

    Campos obrigatórios em toda linha: "t" (time.time()), "no" e "evento".
    Eventos obrigatórios (usados na análise e no vídeo):
        "inicio", "vizinho_up", "vizinho_down", "rota_instalada", "rota_removida", "fim"
    """

    @abstractmethod
    def registrar(self, evento: str, **campos: object) -> None:
        raise NotImplementedError


class Agente(ABC):
    """Laço principal do roteador."""

    @abstractmethod
    def executar(self) -> None:
        """Roda até receber SIGTERM. Ao sair: TabelaKernel.limpar() e evento "fim"."""
        raise NotImplementedError

    @abstractmethod
    def parar(self) -> None:
        raise NotImplementedError


def descobrir_interfaces() -> list[Interface]:
    """Interfaces IPv4 do roteador, exceto loopback. Deve ler do kernel (ex.: ip -j addr)."""
    raise NotImplementedError


def criar_agente(config: Config) -> Agente:
    """Monta o Agente com as implementações concretas escolhidas pela dupla."""
    raise NotImplementedError("algoritmo próprio ainda não implementado: veja algoritmo/CONTRATO.md")
