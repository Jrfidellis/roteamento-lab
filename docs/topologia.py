"""Gera docs/topologia.svg (diagrama da topologia usado no README).

Uso: python3 docs/topologia.py docs/topologia.svg
"""
import math, sys

W, H = 1400, 960
C_ROUTER = "#1f6fb2"
C_HOST = "#56636e"
C_SW = "#1c8a7e"
C_LINK = "#3d4a57"
C_LAN = "#8a96a3"
C_FAIL = "#d9480f"
C_TXT = "#1f2933"
C_MUTED = "#5f6b76"
FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"

routers = {  # nome: (x, y, rid, lado do rótulo)
    "A": (330, 420, "1.1.1.1", "up"),
    "B": (1150, 180, "2.2.2.2", "up"),
    "C": (850, 320, "3.3.3.3", "left-down"),
    "D": (850, 520, "4.4.4.4", "left-up"),
    "E": (1150, 660, "5.5.5.5", "down"),
}
hosts = {  # nome: (x, y, roteador, N)
    "ha": (90, 420, "A", 1),
    "hb": (1320, 180, "B", 2),
    "hc": (1015, 320, "C", 3),
    "hd": (1015, 520, "D", 4),
    "he": (1320, 660, "E", 5),
}
switches = {  # nome: (x, y, prefixo, membros, lado do rótulo)
    "sw0": (590, 235, "10.0.10.0/24", "A, B, C", "up"),
    "sw1": (590, 605, "10.0.20.0/24", "A, D, E", "down"),
}
octet = {r: i + 1 for i, r in enumerate("ABCDE")}

out = []
def add(s): out.append(s)

def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def text(x, y, s, size=12, weight="normal", anchor="middle", color=C_TXT, font=FONT, extra=""):
    add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}" fill="{color}" {extra}>{esc(s)}</text>')

def pill(x, y, s, color=C_LINK, size=11.5, bold=False):
    w = len(s) * size * 0.62 + 14
    h = size + 9
    add(f'<rect x="{x - w/2:.1f}" y="{y - h/2:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h/2:.1f}" '
        f'fill="#ffffff" stroke="{color}" stroke-width="1.2"/>')
    text(x, y + size * 0.36, s, size=size, font=MONO, color=color, weight="bold" if bold else "normal")

def line(p, q, color=C_LINK, width=3, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<line x1="{p[0]}" y1="{p[1]}" x2="{q[0]}" y2="{q[1]}" stroke="{color}" '
        f'stroke-width="{width}" stroke-linecap="round"{d}/>')

def octet_label(r, other, s, side=1, dist=50, off=13, color=C_ROUTER):
    """Rótulo '.N' perto do roteador r, ao longo do enlace até 'other'."""
    x, y = routers[r][:2]
    dx, dy = other[0] - x, other[1] - y
    L = math.hypot(dx, dy); ux, uy = dx / L, dy / L
    px, py = -uy * side, ux * side
    lx, ly = x + ux * dist + px * off, y + uy * dist + py * off
    text(lx, ly + 4, s, size=12, weight="bold", font=MONO, color=color)

# ---------- ícones ----------
def router_icon(x, y, r=30):
    add(f'<g transform="translate({x},{y})">')
    add(f'<circle r="{r}" fill="{C_ROUTER}" stroke="#134a7a" stroke-width="2"/>')
    # quatro setas: duas para dentro (diagonal ↘ ↖) e duas para fora, no estilo do símbolo clássico
    a = r * 0.72
    for ang, inward in ((45, True), (225, True), (135, False), (315, False)):
        t = math.radians(ang)
        ox, oy = math.cos(t) * a, math.sin(t) * a
        ix, iy = math.cos(t) * 5, math.sin(t) * 5
        (sx, sy), (ex, ey) = ((ox, oy), (ix, iy)) if inward else ((ix, iy), (ox, oy))
        add(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#fff" stroke-width="3" stroke-linecap="round"/>')
        # ponta
        hx, hy = ex - sx, ey - sy
        L = math.hypot(hx, hy); hx, hy = hx / L, hy / L
        b1 = (ex - hx * 7 + -hy * 5, ey - hy * 7 + hx * 5)
        b2 = (ex - hx * 7 - -hy * 5, ey - hy * 7 - hx * 5)
        add(f'<polygon points="{ex + hx*2:.1f},{ey + hy*2:.1f} {b1[0]:.1f},{b1[1]:.1f} {b2[0]:.1f},{b2[1]:.1f}" fill="#fff"/>')
    add('</g>')

def host_icon(x, y):
    add(f'<g transform="translate({x},{y})">')
    add(f'<rect x="-24" y="-22" width="48" height="33" rx="4" fill="{C_HOST}" stroke="#39434b" stroke-width="1.5"/>')
    add('<rect x="-19" y="-17" width="38" height="23" rx="2" fill="#dbe7f3"/>')
    add('<path d="M-13 1 L-5 -7 L1 -2 L9 -11 L15 -5" fill="none" stroke="#1f6fb2" stroke-width="1.6" stroke-linejoin="round"/>')
    add(f'<rect x="-5" y="11" width="10" height="7" fill="{C_HOST}"/>')
    add(f'<rect x="-15" y="17" width="30" height="5" rx="2" fill="{C_HOST}"/>')
    add('</g>')

def switch_icon(x, y, w=96, h=40):
    add(f'<g transform="translate({x},{y})">')
    add(f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="6" fill="{C_SW}" stroke="#12594f" stroke-width="2"/>')
    for yy, direction in ((-8, 1), (8, -1)):
        x0, x1 = (-30, 30) if direction == 1 else (30, -30)
        add(f'<line x1="{x0}" y1="{yy}" x2="{x1}" y2="{yy}" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>')
        add(f'<polygon points="{x1 + direction*3},{yy} {x1 - direction*6},{yy-5} {x1 - direction*6},{yy+5}" fill="#fff"/>')
    add('</g>')

def bolt(x, y, color=C_FAIL):
    add(f'<g transform="translate({x},{y})">')
    add(f'<circle r="15" fill="#fff" stroke="{color}" stroke-width="2"/>')
    add(f'<polygon points="3,-11 -7,2 -1,2 -4,11 7,-3 1,-3" fill="{color}"/>')
    add('</g>')

# ---------- documento ----------
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
text(40, 48, "Topologia do laboratório de roteamento", size=24, weight="bold", anchor="start")
text(40, 74, "5 roteadores FRRouting, 5 hosts e 9 redes /24, um container Docker por nó. "
     "Área OSPF única (área 0) e mesma topologia para OSPF, RIP e o algoritmo próprio.",
     size=13.5, anchor="start", color=C_MUTED)

P = {k: v[:2] for k, v in {**routers, **hosts}.items()}
P.update({k: v[:2] for k, v in switches.items()})

# enlaces de LAN (fino, cinza)
for h, (x, y, r, n) in hosts.items():
    line((x, y), P[r], color=C_LAN, width=2.5)

# segmentos compartilhados
for sw, members in (("sw0", "ABC"), ("sw1", "ADE")):
    for r in members:
        fail = sw == "sw1" and r == "A"
        line(P[sw], P[r], color=C_FAIL if fail else C_LINK, width=3)

# ponto a ponto
line(P["B"], P["E"], width=3.5)
line(P["C"], P["D"], width=3.5)

# rótulos de rede sobre os enlaces
for h, (x, y, r, n) in hosts.items():
    rx, ry = P[r]
    pill((x + rx) / 2 + (8 if x < rx else -6), y, f"10.0.{n}.0/24", color=C_MUTED, size=10.5)
pill(1150, 420, "be  10.0.25.0/24", bold=True)
pill(850, 420, "cd  10.0.34.0/24", bold=True)

# falha
mx, my = (P["A"][0] + P["sw1"][0]) / 2, (P["A"][1] + P["sw1"][1]) / 2
bolt(mx, my)
text(mx - 22, my + 36, "enlace derrubado no teste de falha", size=12, weight="bold", anchor="end", color=C_FAIL)
text(mx - 22, my + 52, "make falha NO=a REDE=10.0.20.", size=11.5, anchor="end", color=C_FAIL, font=MONO)

# octetos das interfaces dos roteadores
LBL = [  # roteador, destino, lado
    ("A", "sw0", 1), ("A", "sw1", 1),
    ("B", "sw0", 1), ("B", "E", -1),
    ("C", "sw0", 1), ("C", "D", 1),
    ("D", "sw1", -1), ("D", "C", -1),
    ("E", "sw1", -1), ("E", "B", 1),
]
for r, dst, side in LBL:
    s = ".1" if dst in hosts else f".{octet[r]}"
    octet_label(r, P[dst], s, side=side)

# ícones por cima das linhas
for sw, (x, y, pref, mem, side) in switches.items():
    switch_icon(x, y)
    if side == "up":
        text(x, y - 66, sw, size=16, weight="bold", color=C_SW)
        text(x, y - 48, pref, size=12.5, font=MONO, weight="bold")
        text(x, y - 32, f"segmento compartilhado: {mem}", size=11.5, color=C_MUTED)
    else:
        text(x, y + 44, sw, size=16, weight="bold", color=C_SW)
        text(x, y + 62, pref, size=12.5, font=MONO, weight="bold")
        text(x, y + 78, f"segmento compartilhado: {mem}", size=11.5, color=C_MUTED)

for r, (x, y, rid, side) in routers.items():
    router_icon(x, y)
    if side == "up":
        text(x, y - 56, f"Roteador {r}", size=15, weight="bold")
        text(x, y - 40, f"RID {rid}", size=11.5, font=MONO, color=C_MUTED)
    elif side == "down":
        text(x, y + 52, f"Roteador {r}", size=15, weight="bold")
        text(x, y + 68, f"RID {rid}", size=11.5, font=MONO, color=C_MUTED)
    else:
        dy = 34 if side == "left-down" else -26
        text(x - 34, y + dy, f"Roteador {r}", size=15, weight="bold", anchor="end")
        text(x - 34, y + dy + 16, f"RID {rid}", size=11.5, font=MONO, color=C_MUTED, anchor="end")

for h, (x, y, r, n) in hosts.items():
    host_icon(x, y)
    text(x, y + 42, h, size=14, weight="bold")
    text(x, y + 58, f"10.0.{n}.10", size=11.5, font=MONO)
    text(x, y + 73, f"gw 10.0.{n}.1", size=11, font=MONO, color=C_MUTED)

# ---------- legenda ----------
top = 770
add(f'<line x1="40" y1="{top - 22}" x2="{W - 40}" y2="{top - 22}" stroke="#d5dbe1" stroke-width="1"/>')

def card(x, title, rows, w=300):
    text(x, top, title, size=13.5, weight="bold", anchor="start")
    for i, row in enumerate(rows):
        yy = top + 24 + i * 19
        if isinstance(row, tuple):
            s, color = row
        else:
            s, color = row, C_TXT
        indent = 12 if s.startswith("  ") else 0
        text(x + indent, yy, s.strip(), size=12, anchor="start", color=color)

# símbolos
x0 = 40
text(x0, top, "Símbolos", size=13.5, weight="bold", anchor="start")
add(f'<g transform="translate({x0 + 14},{top + 28}) scale(0.5)">'); router_icon(0, 0); add('</g>')
text(x0 + 36, top + 32, "roteador FRR 10.2.1", size=12, anchor="start")
add(f'<g transform="translate({x0 + 14},{top + 62}) scale(0.5)">'); host_icon(0, 0); add('</g>')
text(x0 + 36, top + 66, "host Alpine 3.20", size=12, anchor="start")
add(f'<g transform="translate({x0 + 14},{top + 94}) scale(0.3)">'); switch_icon(0, 0); add('</g>')
text(x0 + 36, top + 98, "bridge Docker (switch)", size=12, anchor="start")
line((x0, top + 124), (x0 + 28, top + 124), width=3)
text(x0 + 36, top + 128, "enlace de trânsito", size=12, anchor="start")
line((x0, top + 148), (x0 + 28, top + 148), color=C_LAN, width=2.5)
text(x0 + 36, top + 152, "LAN de acesso", size=12, anchor="start")
line((x0, top + 172), (x0 + 28, top + 172), color=C_FAIL, width=3)
text(x0 + 36, top + 176, "enlace do teste de falha", size=12, anchor="start")

card(250, "Endereçamento", [
    "LAN N: 10.0.N.0/24, roteador .1, host .10",
    "Trânsito: o roteador N usa sempre .N",
    "  (A = .1, B = .2, C = .3, D = .4, E = .5)",
    "Router ID: N.N.N.N (1.1.1.1 até 5.5.5.5)",
    "Hosts: rota default pelo roteador da LAN",
    (".254 em cada rede: gateway do Docker,", C_MUTED),
    ("rota default removida nos roteadores", C_MUTED),
])
card(590, "Planos de controle (um por vez)", [
    "OSPFv2: área 0, custo 1 em todo enlace",
    "  (veth de 10 Gbit/s, ref. 100 Mbit/s)",
    "  toda rede é broadcast, com DR/BDR",
    "RIPv2: timers 30 / 180 / 120 s",
    "Próprio: UDP 5555, rotas proto 99",
    "  hello 5 s, morto 15 s, anúncio 10 s",
    ("rp_filter desligado, ip_forward ligado", C_MUTED),
])
card(935, "Caminhos de ha até he", [
    ("1. A → sw1 → E   (3 saltos no traceroute)", C_TXT),
    "2. A → sw0 → B → be → E",
    "3. A → sw0 → C → cd → D → sw1 → E",
    "",
    ("Sem o enlace de A em sw1, OSPF e RIP", C_FAIL),
    ("convergem para o caminho 2 (menor custo", C_FAIL),
    ("e menos saltos que o caminho 3).", C_FAIL),
])
add('</svg>')
open(sys.argv[1], "w").write("\n".join(out))
