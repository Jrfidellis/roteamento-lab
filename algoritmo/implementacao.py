"""Algoritmo próprio "Gravidade".

Cada roteador mede o tempo de ida e volta (RTT) até os vizinhos, dá uma
nota (custo) a cada enlace e escolhe, para cada rede, o caminho de menor custo total.
 
  - custo do enlace = RTT² / massa   (massa = fração dos hellos que chegaram)
  - cada rota anunciada leva a lista de roteadores por onde passa; quem se vê nela ignora
    o anúncio, e assim não se formam loops
  - vizinho calado por tempo_morto_s é considerado caído e as rotas são refeitas
 
Explicação completa: algoritmo-gravidade.md
"""

from __future__ import annotations

import json
import math
import os
import select
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import Any, Callable

from .config import Config
from .constantes import DIR_LOG, PORTA_UDP, PROTO_KERNEL
from .interfaces import (
    Agente,
    CalculoRotas,
    Codec,
    Metrica,
    RegistroEventos,
    TabelaKernel,
    Transporte,
    Vizinhanca,
)
from .tipos import Interface, Mensagem, Rota, Vizinho

# ======================================================================
# MAPA DO CÓDIGO
#
# Cada roteador roda UM "agente". Várias vezes por segundo ele:
#   1. escuta as mensagens dos vizinhos;
#   2. diz "estou vivo" (hello) de tempos em tempos;
#   3. descobre o melhor caminho até cada rede;
#   4. coloca esse caminho na tabela do sistema (comando "ip route");
#   5. conta aos vizinhos o que sabe (anúncio).
#
# O arquivo tem 8 blocos, nesta ordem:
#   1. Codec          traduz mensagem <-> texto JSON
#   2. Transporte     envia e recebe pela rede (UDP, porta 5555)
#   3. Métrica        dá a "nota" (custo) de cada enlace
#   4. Vizinhança     lista quem está vivo e mede o tempo de ida e volta (RTT)
#   5. CalculoRotas   escolhe o caminho de menor custo para cada rede
#   6. TabelaKernel   escreve as rotas no sistema (sempre com proto 99)
#   7. Registro       grava o log de eventos em JSON
#   8. Agente         o laço principal que junta tudo
# ======================================================================

# --- parâmetros do algoritmo (justificar no README) ---
PISO_RTT_MS = 1.0          # abaixo disso o RTT é ruído de agendamento; custo mínimo do enlace = 1
ALFA_RTT = 0.3             # peso da amostra nova na média móvel do RTT
ALFA_PERDA = 0.2           # idem para a perda de hellos
MASSA_MIN = 0.1            # massa nunca cai abaixo disso (evita custo infinito por perda alta)
HISTERESE = 0.25           # custo do enlace só muda se variar mais que 25 % (evita flapping)
INTERVALO_MIN_DISPARO_S = 0.5   # espaço mínimo entre anúncios disparados por mudança
RESYNC_KERNEL_S = 5.0      # reconcilia o kernel com a tabela desejada mesmo sem mudança
TIMEOUT_RECEBER_S = 0.1


# ---------------------------------------------------------------- 1. CODEC
# Transforma cada mensagem em texto JSON (para enviar) e o texto de volta em mensagem
# (ao receber). Se chegar lixo, levanta ValueError em vez de aceitar.
def _rejeitar_constante(nome: str) -> None:
    raise ValueError(f"constante JSON inválida: {nome}")


class GravidadeCodec(Codec):
    """JSON compacto. Chaves curtas (t, o, s, c) para reduzir bytes de controle."""

    def codificar(self, mensagem: Mensagem) -> bytes:
        return json.dumps(
            {"t": mensagem.tipo, "o": mensagem.origem, "s": mensagem.sequencia, "c": mensagem.corpo},
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def decodificar(self, dados: bytes) -> Mensagem:
        try:
            d = json.loads(dados.decode("utf-8"), parse_constant=_rejeitar_constante)
        except (UnicodeDecodeError, ValueError) as e:
            raise ValueError("pacote malformado") from e
        if not isinstance(d, dict):
            raise ValueError("pacote não é um objeto")
        tipo, origem, seq, corpo = d.get("t"), d.get("o"), d.get("s"), d.get("c", {})
        if not isinstance(tipo, str) or not isinstance(origem, str):
            raise ValueError("tipo/origem inválidos")
        if isinstance(seq, bool) or not isinstance(seq, int):
            raise ValueError("sequência inválida")
        if not isinstance(corpo, dict):
            raise ValueError("corpo inválido")
        return Mensagem(tipo=tipo, origem=origem, sequencia=seq, corpo=corpo)


# ---------------------------------------------------------------- 2. TRANSPORTE
# Cuida de enviar e receber pela rede. Usa UDP na porta 5555 (exigência do contrato).
# "Broadcast" = mandar para todos os vizinhos da mesma rede de uma vez só.
class GravidadeTransporte(Transporte):
    """UDP/5555 com broadcast de rede por interface e unicast para respostas."""

    def __init__(self, codec: Codec):
        self.codec = codec
        self.sock: socket.socket | None = None
        self.interfaces: list[Interface] = []
        self._proprios: set[IPv4Address] = set()
        self.descartados = 0

    def abrir(self, interfaces: list[Interface]) -> None:
        self.interfaces = list(interfaces)
        self._proprios = {i.endereco.ip for i in interfaces}
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("0.0.0.0", PORTA_UDP))
        s.setblocking(False)
        self.sock = s

    def enviar(self, mensagem: Mensagem, interface: Interface,
               destino: IPv4Address | None = None) -> None:
        if self.sock is None:
            return
        alvo = str(destino) if destino is not None else str(interface.rede.broadcast_address)
        try:
            self.sock.sendto(self.codec.codificar(mensagem), (alvo, PORTA_UDP))
        except OSError:
            pass  # enlace caído no meio do envio: o timeout de vizinhança cuida do resto

    def _interface_de(self, ip: IPv4Address) -> Interface | None:
        for i in self.interfaces:
            if ip in i.rede:
                return i
        return None

    def receber(self, timeout_s: float) -> list[tuple[Mensagem, IPv4Address, Interface]]:
        """Bloqueia até chegar o primeiro pacote (ou estourar timeout_s), esvazia a fila e
        devolve NA HORA. Não espera o timeout inteiro: isso inflaria o RTT medido."""
        if self.sock is None:
            return []
        try:
            prontos, _, _ = select.select([self.sock], [], [], max(0.0, timeout_s))
        except (OSError, ValueError):
            return []
        if not prontos:
            return []
        saida: list[tuple[Mensagem, IPv4Address, Interface]] = []
        for _ in range(256):
            try:
                dados, (ip, _porta) = self.sock.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                remetente = IPv4Address(ip)
            except ValueError:
                continue
            if remetente in self._proprios:
                continue  # eco do próprio broadcast
            iface = self._interface_de(remetente)
            if iface is None:
                continue
            try:
                msg = self.codec.decodificar(dados)
            except ValueError:
                self.descartados += 1
                continue
            saida.append((msg, remetente, iface))
        return saida

    def fechar(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None


# ---------------------------------------------------------------- 3. MÉTRICA
# Dá a nota (custo) de cada enlace:  custo = RTT² / massa.
# RTT = tempo de ida e volta; massa = fração dos hellos que chegaram. Menor custo = melhor.
@dataclass
class VizinhoMedido(Vizinho):
    """Vizinho com as medições que alimentam a métrica."""

    rtt_ms: float = PISO_RTT_MS
    perda: float = 0.0
    seq_eco: int = -1


class GravidadeMetrica(Metrica):
    """custo = 1/F = d² / m, com F = m / d² (gravitação)."""

    def custo(self, vizinho: Vizinho) -> float:
        d = max(PISO_RTT_MS, float(getattr(vizinho, "rtt_ms", PISO_RTT_MS)))
        perda = min(max(float(getattr(vizinho, "perda", 0.0)), 0.0), 1.0 - MASSA_MIN)
        massa = 1.0 - perda
        return (d * d) / massa


# ---------------------------------------------------------------- 4. VIZINHANÇA
# Guarda a lista de vizinhos vivos, mede RTT e perda de cada um e
# remove quem ficou tempo_morto_s sem dar sinal.
class GravidadeVizinhanca(Vizinhanca):
    def __init__(self, tempo_morto_s: float, metrica: Metrica):
        self.tempo_morto_s = tempo_morto_s
        self.metrica = metrica
        self._v: dict[IPv4Address, VizinhoMedido] = {}

    def conhece(self, ip: IPv4Address) -> bool:
        return ip in self._v

    def obter(self, ip: IPv4Address) -> VizinhoMedido | None:
        return self._v.get(ip)

    def processar(self, mensagem: Mensagem, remetente: IPv4Address, interface: Interface) -> None:
        agora = time.monotonic()
        v = self._v.get(remetente)
        if v is not None:
            v.visto_em = agora
            v.router_id = mensagem.origem
            v.interface = interface

        if mensagem.tipo != "eco":
            return
        ts, seq = mensagem.corpo.get("ts"), mensagem.corpo.get("seq")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            return
        if isinstance(seq, bool) or not isinstance(seq, int):
            return
        rtt = (agora - ts) * 1000.0
        if not (0.0 <= rtt < 60_000.0):
            return

        if v is None:  # primeiro eco: enlace comprovadamente bidirecional
            v = VizinhoMedido(
                router_id=mensagem.origem, endereco=remetente, interface=interface,
                visto_em=agora, rtt_ms=max(PISO_RTT_MS, rtt), perda=0.0, seq_eco=seq,
            )
            v.custo = self.metrica.custo(v)
            self._v[remetente] = v
            return

        v.rtt_ms = (1 - ALFA_RTT) * v.rtt_ms + ALFA_RTT * rtt
        if seq > v.seq_eco:
            for _ in range(min(seq - v.seq_eco - 1, 10)):   # hellos que não voltaram
                v.perda = (1 - ALFA_PERDA) * v.perda + ALFA_PERDA
            v.perda = (1 - ALFA_PERDA) * v.perda            # este voltou
            v.seq_eco = seq
        novo = self.metrica.custo(v)
        if v.custo <= 0 or abs(novo - v.custo) / v.custo > HISTERESE:
            v.custo = novo

    def vizinhos(self) -> list[Vizinho]:
        return list(self._v.values())

    def expirar(self, agora: float) -> list[Vizinho]:
        mortos = [ip for ip, v in self._v.items() if agora - v.visto_em > self.tempo_morto_s]
        return [self._v.pop(ip) for ip in mortos]


# ---------------------------------------------------------------- 5. CÁLCULO DE ROTAS
# O "cérebro": guarda o que cada vizinho anunciou e escolhe, para cada rede, o caminho
# de menor custo. Ignora anúncios cujo caminho já passa por este roteador (evita loop).
@dataclass(frozen=True)
class _Melhor:
    destino: IPv4Network
    custo: float
    caminho: tuple[str, ...]          # começa neste roteador e termina na origem da rede
    proximo_salto: IPv4Address | None
    interface: Interface


class GravidadeCalculoRotas(CalculoRotas):
    def __init__(self, router_id: str):
        self.router_id = router_id
        # tabela anunciada por cada vizinho vivo: rede -> (custo do vizinho até ela, caminho)
        self._tabelas: dict[IPv4Address, dict[IPv4Network, tuple[float, tuple[str, ...]]]] = {}
        self._melhores: dict[IPv4Network, _Melhor] = {}
        self._seq = 0

    def processar(self, mensagem: Mensagem, vizinho: Vizinho) -> bool:
        if mensagem.tipo != "anuncio":
            return False
        bruto = mensagem.corpo.get("rotas")
        if not isinstance(bruto, list):
            return False
        nova: dict[IPv4Network, tuple[float, tuple[str, ...]]] = {}
        for item in bruto:
            try:
                rede = IPv4Network(item["rede"], strict=True)
                custo = float(item["custo"])
                caminho_bruto = item["caminho"]
                if not isinstance(caminho_bruto, list):
                    continue
                caminho = tuple(str(x) for x in caminho_bruto)
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(custo) or custo < 0 or not caminho:
                continue
            if caminho[0] != vizinho.router_id:
                continue                      # anúncio incoerente com quem o enviou
            if self.router_id in caminho:
                continue                      # loop: a rota já passa por mim
            nova[rede] = (custo, caminho)
        antiga = self._tabelas.get(vizinho.endereco)
        self._tabelas[vizinho.endereco] = nova   # estado soft: substitui a tabela inteira
        return antiga != nova

    def vizinho_caiu(self, vizinho: Vizinho) -> None:
        self._tabelas.pop(vizinho.endereco, None)

    def calcular(self, vizinhos: list[Vizinho], conectadas: list[Interface]) -> list[Rota]:
        vivos = {v.endereco for v in vizinhos}
        for ip in [ip for ip in self._tabelas if ip not in vivos]:
            del self._tabelas[ip]

        melhores: dict[IPv4Network, _Melhor] = {}
        chaves: dict[IPv4Network, tuple[float, int, int]] = {}
        diretas: set[IPv4Network] = set()
        for iface in conectadas:
            diretas.add(iface.rede)
            melhores[iface.rede] = _Melhor(iface.rede, 0.0, (self.router_id,), None, iface)

        for v in sorted(vizinhos, key=lambda x: int(x.endereco)):
            for rede, (custo, caminho) in self._tabelas.get(v.endereco, {}).items():
                if rede in diretas:
                    continue
                total = v.custo + custo
                # menor custo; empate -> menos saltos; empate -> menor IP (determinístico)
                chave = (round(total, 6), len(caminho), int(v.endereco))
                if rede not in melhores or chave < chaves[rede]:
                    chaves[rede] = chave
                    melhores[rede] = _Melhor(
                        rede, total, (self.router_id,) + caminho, v.endereco, v.interface
                    )

        self._melhores = melhores
        return [
            Rota(destino=m.destino, proximo_salto=m.proximo_salto,
                 interface=m.interface.nome, metrica=m.custo)
            for _, m in sorted(melhores.items(), key=lambda kv: (int(kv[0].network_address), kv[0].prefixlen))
        ]

    def anuncio(self, interface: Interface) -> Mensagem:
        self._seq += 1
        rotas = []
        for rede, m in sorted(self._melhores.items(),
                              key=lambda kv: (int(kv[0].network_address), kv[0].prefixlen)):
            if m.interface.nome == interface.nome:
                continue                      # split horizon por interface
            rotas.append({"rede": str(rede), "custo": round(m.custo, 3), "caminho": list(m.caminho)})
        return Mensagem(tipo="anuncio", origem=self.router_id, sequencia=self._seq,
                        corpo={"rotas": rotas})


# ---------------------------------------------------------------- 6. TABELA DO KERNEL
# Escreve as rotas escolhidas no sistema com "ip route" (sempre proto 99).
# Só mexe no que mudou e nunca toca nas rotas conectadas.
Executor = Callable[[list[str]], "tuple[int, str]"]


def _executar_ip(args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return r.returncode, r.stdout


class GravidadeTabelaKernel(TabelaKernel):
    """Só toca em rotas proto 99 e só chama `ip` quando há diferença real."""

    def __init__(self, executor: Executor | None = None):
        self._run: Executor = executor or _executar_ip

    def listar(self) -> list[Rota]:
        rc, saida = self._run(["ip", "-j", "route", "show", "proto", str(PROTO_KERNEL)])
        if rc != 0 or not saida.strip():
            return []
        try:
            dados = json.loads(saida)
        except ValueError:
            return []
        rotas = []
        for item in dados:
            dst, gw, dev = item.get("dst"), item.get("gateway"), item.get("dev")
            if not dst or not gw or not dev or dst == "default":
                continue
            try:
                rotas.append(Rota(IPv4Network(dst, strict=False), IPv4Address(gw), dev,
                                  float(item.get("metric", 0))))
            except ValueError:
                continue
        return rotas

    def sincronizar(self, rotas: list[Rota]) -> tuple[list[Rota], list[Rota]]:
        desejadas = {r.destino: r for r in rotas if r.proximo_salto is not None}
        atuais: dict[IPv4Network, list[Rota]] = {}
        for r in self.listar():
            atuais.setdefault(r.destino, []).append(r)

        instaladas: list[Rota] = []
        removidas: list[Rota] = []

        for destino, r in desejadas.items():
            metrica = max(1, int(round(r.metrica)))
            existentes = atuais.get(destino, [])
            correta = any(e.proximo_salto == r.proximo_salto and e.interface == r.interface
                          and int(e.metrica) == metrica for e in existentes)
            if not correta:
                rc, _ = self._run(["ip", "route", "replace", str(destino), "via", str(r.proximo_salto),
                                   "dev", r.interface, "proto", str(PROTO_KERNEL), "metric", str(metrica)])
                if rc != 0:
                    continue   # mantém o que já estava; tenta de novo no próximo resync
                if not any(e.proximo_salto == r.proximo_salto and e.interface == r.interface
                           for e in existentes):
                    instaladas.append(r)   # mudança de salto/interface; só de métrica não é evento
            # `replace` com métrica diferente cria outra rota em vez de trocar: apaga as antigas
            for e in existentes:
                if int(e.metrica) != metrica:
                    self._run(["ip", "route", "del", str(destino), "proto", str(PROTO_KERNEL),
                               "metric", str(int(e.metrica))])

        for destino, lista in atuais.items():
            if destino in desejadas:
                continue
            ok = True
            for e in lista:
                rc, _ = self._run(["ip", "route", "del", str(destino), "proto", str(PROTO_KERNEL),
                                   "metric", str(int(e.metrica))])
                ok = ok and rc == 0
            if ok:
                removidas.append(lista[0])
        return instaladas, removidas

    def limpar(self) -> None:
        self._run(["ip", "route", "flush", "proto", str(PROTO_KERNEL)])


# ---------------------------------------------------------------- 7. LOG DE EVENTOS
# Grava cada evento (vizinho subiu, rota instalada...) numa linha JSON do arquivo de log.
class GravidadeRegistroEventos(RegistroEventos):
    def __init__(self, no: str):
        self.no = no
        os.makedirs(DIR_LOG, exist_ok=True)
        self.arquivo = os.path.join(DIR_LOG, f"{no}.jsonl")
        self._f = open(self.arquivo, "a", encoding="utf-8", buffering=1)

    def registrar(self, evento: str, **campos: Any) -> None:
        linha = {**campos, "t": time.time(), "no": self.no, "evento": evento}
        try:
            self._f.write(json.dumps(linha, default=str) + "\n")
        except (OSError, ValueError):
            pass

    def fechar(self) -> None:
        try:
            self._f.close()
        except OSError:
            pass


# ---------------------------------------------------------------- 8. AGENTE
# O laço principal: junta todas as peças e roda até receber SIGTERM (make down).
def _assinatura(rotas: list[Rota]) -> tuple:
    return tuple(sorted((str(r.destino), str(r.proximo_salto), r.interface, round(float(r.metrica), 3))
                        for r in rotas))


class GravidadeAgente(Agente):
    def __init__(self, config: Config, interfaces: list[Interface],
                 transporte: Transporte | None = None, kernel: TabelaKernel | None = None):
        self.config = config
        self.interfaces = list(interfaces)
        self.rodando = True

        self.codec = GravidadeCodec()
        self.transporte = transporte or GravidadeTransporte(self.codec)
        self.metrica = GravidadeMetrica()
        self.vizinhanca = GravidadeVizinhanca(config.tempo_morto_s, self.metrica)
        self.calculo = GravidadeCalculoRotas(config.router_id)
        self.kernel = kernel or GravidadeTabelaKernel()
        self.logger = GravidadeRegistroEventos(config.no)

        self.intervalo_anuncio = float(config.intervalo_anuncio_s)
        hello = getattr(config, "intervalo_hello_s", None)
        hello = float(hello) if hello else min(self.intervalo_anuncio, config.tempo_morto_s / 4)
        # tolera perder 2 hellos seguidos antes de declarar o vizinho morto
        self.intervalo_hello = max(0.1, min(hello, config.tempo_morto_s / 3))

        self._seq_hello = 0
        self._seq_msg = 0

    # -- utilidades
    def _proxima_seq(self) -> int:
        self._seq_msg += 1
        return self._seq_msg

    def _enviar_hello(self) -> None:
        self._seq_hello += 1
        for iface in self.interfaces:
            self.transporte.enviar(
                Mensagem("hello", self.config.router_id, self._proxima_seq(),
                         {"seq": self._seq_hello, "ts": time.monotonic()}),
                iface)

    def _responder_hello(self, msg: Mensagem, remetente: IPv4Address, iface: Interface) -> None:
        ts, seq = msg.corpo.get("ts"), msg.corpo.get("seq")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            return
        if isinstance(seq, bool) or not isinstance(seq, int):
            return
        self.transporte.enviar(
            Mensagem("eco", self.config.router_id, self._proxima_seq(), {"seq": seq, "ts": ts}),
            iface, destino=remetente)

    # -- laço principal
    def executar(self) -> None:
        self.logger.registrar(
            "inicio", router_id=self.config.router_id,
            interfaces=[f"{i.nome}={i.endereco}" for i in self.interfaces],
            hello_s=self.intervalo_hello, anuncio_s=self.intervalo_anuncio,
            tempo_morto_s=self.config.tempo_morto_s)
        try:
            signal.signal(signal.SIGTERM, lambda *_: self.parar())
            signal.signal(signal.SIGINT, lambda *_: self.parar())
        except ValueError:
            pass  # fora da thread principal (testes)
        self.transporte.abrir(self.interfaces)
        try:
            self._laco()
        finally:
            self.kernel.limpar()
            self.transporte.fechar()
            self.logger.registrar("fim")
            self.logger.fechar()

    def _laco(self) -> None:
        t_hello = t_anuncio = t_sync = 0.0
        assinatura_anterior: tuple | None = None
        anuncio_pendente = True

        while self.rodando:
            chegaram = self.transporte.receber(timeout_s=TIMEOUT_RECEBER_S)
            agora = time.monotonic()

            # 1) responde hellos primeiro: quanto antes o eco sai, mais fiel é o RTT do vizinho
            for msg, remetente, iface in chegaram:
                if msg.origem != self.config.router_id and msg.tipo == "hello":
                    self._responder_hello(msg, remetente, iface)

            # 2) processa tudo
            for msg, remetente, iface in chegaram:
                if msg.origem == self.config.router_id:
                    continue
                conhecia = self.vizinhanca.conhece(remetente)
                self.vizinhanca.processar(msg, remetente, iface)
                v = self.vizinhanca.obter(remetente)
                if v is None:
                    continue
                if not conhecia:
                    self.logger.registrar("vizinho_up", vizinho=str(remetente), router_id=v.router_id,
                                          interface=iface.nome, rtt_ms=round(v.rtt_ms, 3),
                                          custo=round(v.custo, 3))
                    anuncio_pendente = True   # vizinho novo precisa da nossa tabela já
                if msg.tipo == "anuncio":
                    self.calculo.processar(msg, v)

            # 3) hello periódico (antes do trabalho pesado)
            if agora - t_hello >= self.intervalo_hello:
                self._enviar_hello()
                t_hello = agora

            # 4) vizinhos silenciosos
            for v in self.vizinhanca.expirar(agora):
                self.calculo.vizinho_caiu(v)
                self.logger.registrar("vizinho_down", vizinho=str(v.endereco), router_id=v.router_id,
                                      interface=v.interface.nome)

            # 5) tabela desejada; kernel só é tocado quando algo mudou (ou no resync periódico)
            desejadas = self.calculo.calcular(self.vizinhanca.vizinhos(), self.interfaces)
            assinatura = _assinatura(desejadas)
            mudou = assinatura != assinatura_anterior
            if mudou or agora - t_sync >= RESYNC_KERNEL_S:
                instaladas, removidas = self.kernel.sincronizar(desejadas)
                for r in instaladas:
                    self.logger.registrar("rota_instalada", destino=str(r.destino),
                                          via=str(r.proximo_salto), interface=r.interface,
                                          metrica=round(r.metrica, 3))
                for r in removidas:
                    self.logger.registrar("rota_removida", destino=str(r.destino))
                assinatura_anterior = assinatura
                t_sync = agora
            if mudou:
                anuncio_pendente = True

            # 6) anúncios: periódico, ou disparado por mudança respeitando o intervalo mínimo
            desde = agora - t_anuncio
            if desde >= self.intervalo_anuncio or (anuncio_pendente and desde >= INTERVALO_MIN_DISPARO_S):
                for iface in self.interfaces:
                    self.transporte.enviar(self.calculo.anuncio(iface), iface)
                t_anuncio = agora
                anuncio_pendente = False

    def parar(self) -> None:
        self.rodando = False