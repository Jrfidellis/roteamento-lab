"""Gera os gráficos comparativos a partir de resultados/<proto>/metricas.csv.

Uso (sem depender do Python da máquina): make graficos
Saída: resultados/graficos/*.png e resultados/graficos/resumo.md (tabela com todos os valores).
Com ATRASO=1 lê e grava em resultados/atraso/ (cenário com atraso nas redes de trânsito).

Cada protocolo tem uma cor fixa em todos os gráficos, e todo valor aparece escrito
na barra, para que a leitura não dependa só da cor.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RESULTADOS = Path("resultados/atraso") if os.environ.get("ATRASO") == "1" else Path("resultados")
SAIDA = RESULTADOS / "graficos"
ORDEM = ["ospf", "rip", "proprio"]
NOMES = {"ospf": "OSPF", "rip": "RIP", "proprio": "Algoritmo próprio"}
# Três primeiras cores da paleta categórica de referência, validadas para uso conjunto.
CORES = {"ospf": "#2a78d6", "rip": "#eb6834", "proprio": "#1baf7a"}
ROTEADORES = ["a", "b", "c", "d", "e"]

SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_2 = "#52514e"
GRADE = "#e4e3df"

plt.rcParams.update({
    "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "savefig.facecolor": SUPERFICIE,
    "axes.edgecolor": GRADE, "axes.labelcolor": TEXTO_2, "xtick.color": TEXTO_2, "ytick.color": TEXTO_2,
    "text.color": TEXTO, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRADE, "grid.linewidth": 0.8,
    "axes.axisbelow": True,
})


def carregar() -> dict[str, dict[tuple[str, str], tuple[float | None, str]]]:
    dados: dict[str, dict] = {}
    for proto in ORDEM:
        arquivo = RESULTADOS / proto / "metricas.csv"
        if not arquivo.exists():
            continue
        tabela = {}
        with arquivo.open(encoding="utf-8") as f:
            for linha in csv.DictReader(f):
                valor = None if linha["valor"] in ("", "NA") else float(linha["valor"])
                tabela[(linha["metrica"], linha["no"])] = (valor, linha["unidade"])
        dados[proto] = tabela
    return dados


def rotulo(v: float) -> str:
    return f"{v:.0f}" if v >= 100 or v == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")


def barras_por_protocolo(dados, metrica, no, titulo, eixo, arquivo, nota=None):
    protos = [p for p in ORDEM if p in dados and dados[p].get((metrica, no), (None,))[0] is not None]
    if not protos:
        return None
    valores = [dados[p][(metrica, no)][0] for p in protos]
    fig, ax = plt.subplots(figsize=(6, 3.6))
    barras = ax.bar([NOMES[p] for p in protos], valores, width=0.5,
                    color=[CORES[p] for p in protos], edgecolor=SUPERFICIE, linewidth=2)
    for b, v in zip(barras, valores):
        ax.annotate(rotulo(v), (b.get_x() + b.get_width() / 2, b.get_height()),
                    xytext=(0, 4), textcoords="offset points", ha="center", color=TEXTO, fontsize=10)
    ax.set_title(titulo, loc="left")
    ax.set_ylabel(eixo)
    ax.set_ylim(0, max(valores) * 1.18 if max(valores) > 0 else 1)
    ax.tick_params(axis="x", length=0)
    if nota:
        fig.text(0.01, 0.01, nota, fontsize=8, color=TEXTO_2)
    fig.tight_layout(rect=(0, 0.04 if nota else 0, 1, 1))
    caminho = SAIDA / arquivo
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    return caminho


def barras_por_roteador(dados, metrica, titulo, eixo, arquivo):
    protos = [p for p in ORDEM if p in dados and any(dados[p].get((metrica, r), (None,))[0] is not None
                                                     for r in ROTEADORES)]
    if not protos:
        return None
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    largura = 0.8 / len(protos)
    maximo = 0.0
    for i, p in enumerate(protos):
        xs = [j + (i - (len(protos) - 1) / 2) * largura for j in range(len(ROTEADORES))]
        vs = [dados[p].get((metrica, r), (0,))[0] or 0 for r in ROTEADORES]
        maximo = max(maximo, *vs)
        barras = ax.bar(xs, vs, width=largura, color=CORES[p], label=NOMES[p],
                        edgecolor=SUPERFICIE, linewidth=2)
        for b, v in zip(barras, vs):
            ax.annotate(rotulo(v), (b.get_x() + b.get_width() / 2, b.get_height()),
                        xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8, color=TEXTO)
    ax.set_ylim(0, maximo * 1.18 if maximo > 0 else 1)
    ax.set_xticks(range(len(ROTEADORES)), [r.upper() for r in ROTEADORES])
    ax.tick_params(axis="x", length=0)
    ax.set_xlabel("roteador")
    ax.set_ylabel(eixo)
    ax.set_title(titulo, loc="left")
    ax.legend(frameon=False, ncols=len(protos), loc="upper left", bbox_to_anchor=(0, -0.18))
    fig.tight_layout()
    caminho = SAIDA / arquivo
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    return caminho


def resumo(dados) -> Path:
    metricas = [
        ("convergencia_inicial", "rede", "Convergência inicial"),
        ("controle_pacotes_por_min", "total", "Pacotes de controle por minuto (rede)"),
        ("controle_taxa", "total", "Taxa de controle (rede)"),
        ("controle_bytes", "total", "Bytes de controle na janela (rede)"),
        ("tabela_rotas", "a", "Rotas na tabela de A"),
        ("rotas_aprendidas", "a", "Rotas aprendidas por A"),
        ("rtt_medio", "ha-he", "RTT médio ha até he"),
        ("saltos", "ha-he", "Saltos ha até he"),
        ("falha_indisponibilidade", "ha-he", "Indisponibilidade após falha"),
        ("falha_pacotes_perdidos", "ha-he", "Pacotes perdidos na falha"),
        ("falha_controle_pacotes", "total", "Pacotes de controle na janela de falha"),
    ]
    protos = [p for p in ORDEM if p in dados]
    linhas = ["| Métrica | Unidade | " + " | ".join(NOMES[p] for p in protos) + " |",
              "| --- | --- | " + " | ".join("---:" for _ in protos) + " |"]
    for metrica, no, nome in metricas:
        unidade = next((dados[p][(metrica, no)][1] for p in protos if (metrica, no) in dados[p]), "")
        celulas = []
        for p in protos:
            v = dados[p].get((metrica, no), (None,))[0]
            celulas.append("n/d" if v is None else rotulo(v))
        linhas.append(f"| {nome} | {unidade} | " + " | ".join(celulas) + " |")
    caminho = SAIDA / "resumo.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def main() -> None:
    dados = carregar()
    if not dados:
        raise SystemExit("nenhum resultados/<proto>/metricas.csv encontrado: rode make metricas PROTO=<proto>")
    SAIDA.mkdir(parents=True, exist_ok=True)
    gerados = [
        barras_por_protocolo(dados, "convergencia_inicial", "rede", "Tempo de convergência inicial",
                             "segundos", "convergencia.png",
                             "Do início dos containers até todas as tabelas completas e ha alcançar he."),
        barras_por_protocolo(dados, "controle_taxa", "total", "Taxa do tráfego de controle em regime",
                             "bit/s (soma dos 5 roteadores)", "controle_taxa.png"),
        barras_por_protocolo(dados, "controle_pacotes_por_min", "total", "Pacotes de controle por minuto",
                             "pacotes/min (soma dos 5 roteadores)", "controle_pacotes.png"),
        barras_por_roteador(dados, "controle_pacotes", "Pacotes de controle enviados por roteador",
                            "pacotes na janela", "controle_por_roteador.png"),
        barras_por_roteador(dados, "tabela_rotas", "Tamanho da tabela de rotas", "rotas",
                            "tabela_rotas.png"),
        barras_por_protocolo(dados, "rtt_medio", "ha-he", "RTT médio de ha até he", "ms", "rtt.png"),
        barras_por_protocolo(dados, "falha_indisponibilidade", "ha-he",
                             "Indisponibilidade após a queda do enlace A-sw1", "segundos sem resposta",
                             "falha_indisponibilidade.png",
                             "Maior intervalo sem resposta no ping contínuo de ha para he (a cada 0,2 s)."),
        barras_por_protocolo(dados, "falha_pacotes_perdidos", "ha-he", "Pacotes perdidos durante a falha",
                             "pacotes", "falha_perdas.png"),
        resumo(dados),
    ]
    for g in gerados:
        if g:
            print(f"gerado: {g}")


if __name__ == "__main__":
    main()
