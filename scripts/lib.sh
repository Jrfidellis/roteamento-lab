#!/bin/sh
# Definições compartilhadas pelos scripts. Mantém a topologia em um só lugar.

ROTEADORES="a b c d e"
HOSTS="ha hb hc hd he"

# Endereço de cada host (host da LAN do roteador N = 10.0.N.10).
ip_host() {
  case "$1" in ha) echo 10.0.1.10;; hb) echo 10.0.2.10;; hc) echo 10.0.3.10;;
               hd) echo 10.0.4.10;; he) echo 10.0.5.10;; esac
}

# As 9 redes da topologia (5 LANs + 4 de trânsito).
REDES="10.0.1.0/24 10.0.2.0/24 10.0.3.0/24 10.0.4.0/24 10.0.5.0/24 10.0.10.0/24 10.0.20.0/24 10.0.25.0/24 10.0.34.0/24"
N_REDES=9

# Filtro tcpdump do tráfego de controle e nome do protocolo no kernel.
filtro_controle() {
  case "$1" in ospf) echo "ip proto 89";; rip) echo "udp port 520";; proprio) echo "udp port 5555";; esac
}
proto_kernel() {
  case "$1" in ospf) echo ospf;; rip) echo rip;; proprio) echo 99;; esac
}

validar_proto() {
  case "$1" in ospf|rip|proprio) ;; *) echo "PROTO inválido: '$1' (use ospf, rip ou proprio)" >&2; exit 1;; esac
}

ex() { docker compose exec -T "$@"; }

# Interface de um nó que está na rede cujo prefixo começa com $2 (ex.: 10.0.20.).
iface_na_rede() {
  ex "$1" ip -o -4 addr show | awk -v p="$2" 'index($4, p) == 1 {print $2}'
}

# Quantas das 9 redes aparecem na tabela do nó.
redes_na_tabela() {
  ex "$1" sh -c "ip route show | awk '{print \$1}'" | grep -c -x -F -e 10.0.1.0/24 -e 10.0.2.0/24 \
    -e 10.0.3.0/24 -e 10.0.4.0/24 -e 10.0.5.0/24 -e 10.0.10.0/24 -e 10.0.20.0/24 -e 10.0.25.0/24 -e 10.0.34.0/24
}

agora() { python3 -c 'import time; print(time.time())' 2>/dev/null || date +%s; }
