#!/bin/sh
# Derruba ou restaura o enlace de um roteador em uma rede, como arrancar o cabo.
# Uso: scripts/falha.sh down|up <no> <prefixo-da-rede>     ex.: scripts/falha.sh down a 10.0.20.
set -eu
cd "$(dirname "$0")/.."
. scripts/lib.sh
acao="$1"; no="$2"; rede="$3"
iface=$(iface_na_rede "$no" "$rede")
[ -n "$iface" ] || { echo "$no não tem interface na rede $rede" >&2; exit 1; }
ex "$no" ip link set dev "$iface" "$acao"
echo "$no: $iface ($rede*) -> $acao"
