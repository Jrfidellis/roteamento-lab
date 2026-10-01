#!/bin/sh
# Coleta as métricas de um plano de controle, sempre no mesmo cenário, para comparar
# OSPF, RIP e o algoritmo próprio de forma justa. Grava resultados/<proto>/metricas.csv
# (com ATRASO=1, resultados/atraso/<proto>/metricas.csv).
#
# Uso: scripts/metricas.sh <ospf|rip|proprio>
# Variáveis (padrão entre parênteses):
#   CONV_MAX    (180) tempo máximo esperando a convergência inicial, em s
#   JANELA      (120) duração da captura do tráfego de controle em regime, em s
#   FALHA_TOTAL (240) duração do ping contínuo no cenário de falha, em s
#   FALHA_APOS  (10)  segundos de ping antes de derrubar o enlace
#   ATRASO      (0)   1 = redes de trânsito com o atraso de configs/atrasos.conf
#
# Cenário:
#   1. sobe o laboratório do zero e mede o tempo até todos os roteadores conhecerem
#      as 9 redes e ha alcançar he (convergência inicial);
#   2. conta rotas na tabela de cada roteador;
#   3. captura por JANELA s o tráfego de controle enviado por cada roteador;
#   4. mede RTT e número de saltos de ha até he;
#   5. com ping contínuo de ha para he a cada 0,2 s, derruba o enlace de A em sw1
#      e mede o maior intervalo sem resposta (indisponibilidade) e os pacotes perdidos.
set -u
cd "$(dirname "$0")/.."
. scripts/lib.sh
PROTO="${1:?uso: metricas.sh <ospf|rip|proprio>}"; validar_proto "$PROTO"
CONV_MAX="${CONV_MAX:-180}"; JANELA="${JANELA:-120}"
FALHA_TOTAL="${FALHA_TOTAL:-240}"; FALHA_APOS="${FALHA_APOS:-10}"
FILTRO=$(filtro_controle "$PROTO"); KP=$(proto_kernel "$PROTO")
ATRASO="${ATRASO:-0}"; export ATRASO
DIR="$PROTO"; [ "$ATRASO" = 1 ] && DIR="atraso/$PROTO"
OUT="resultados/$DIR"; CSV="$OUT/metricas.csv"
rm -rf "$OUT"; mkdir -p "$OUT"
echo "protocolo,metrica,no,valor,unidade" > "$CSV"
registrar() { echo "$PROTO,$1,$2,$3,$4" >> "$CSV"; }
log() { echo "[$(date +%H:%M:%S)] $*"; }

bytes_pcap() {  # soma do tamanho dos quadros de um pcap dentro do container
  ex "$1" tcpdump -r "$2" -nn -e 2>/dev/null |
    awk '{ if (match($0, /length [0-9]+:/)) s += substr($0, RSTART + 7, RLENGTH - 8) } END { print s + 0 }'
}
pacotes_pcap() { ex "$1" tcpdump -r "$2" -nn 2>/dev/null | wc -l | tr -d ' '; }

# 1. Convergência inicial
log "subindo o laboratório com $PROTO$([ "$ATRASO" = 1 ] && echo ' (cenário com atraso)')"
docker compose down >/dev/null 2>&1
PROTO="$PROTO" docker compose up -d --build >/dev/null 2>&1 || { log "falha ao subir"; exit 1; }
inicio=$(date +%s); convergiu=0
while [ $(( $(date +%s) - inicio )) -lt "$CONV_MAX" ]; do
  completo=1
  for r in $ROTEADORES; do [ "$(redes_na_tabela "$r")" -eq "$N_REDES" ] || { completo=0; break; }; done
  if [ $completo -eq 1 ] && ex ha ping -c 1 -W 1 10.0.5.10 >/dev/null 2>&1; then convergiu=1; break; fi
  sleep 1
done
t_conv=$(( $(date +%s) - inicio ))
if [ $convergiu -eq 0 ]; then
  log "não convergiu em ${CONV_MAX}s; métricas abortadas"
  registrar convergencia_inicial rede NA s
  exit 1
fi
registrar convergencia_inicial rede "$t_conv" s
log "convergiu em ${t_conv}s"

# 2. Tamanho das tabelas
for r in $ROTEADORES; do
  total=$(ex "$r" sh -c "ip route show | grep -c '^[0-9]'" | tr -d '\r')
  aprendidas=$(ex "$r" sh -c "ip route show proto $KP | grep -c '^[0-9]'" | tr -d '\r')
  registrar tabela_rotas "$r" "$total" rotas
  registrar rotas_aprendidas "$r" "$aprendidas" rotas
  ex "$r" ip route show > "$OUT/tabela-$r.txt"
done

# 3. Tráfego de controle em regime
log "capturando tráfego de controle por ${JANELA}s"
for r in $ROTEADORES; do
  docker compose exec -d "$r" sh -c "timeout $JANELA tcpdump -i any -Q out -nn -w /tmp/regime.pcap '$FILTRO' 2>/dev/null"
done
sleep $((JANELA + 3))
tp=0; tb=0
for r in $ROTEADORES; do
  p=$(pacotes_pcap "$r" /tmp/regime.pcap); b=$(bytes_pcap "$r" /tmp/regime.pcap)
  registrar controle_pacotes "$r" "$p" pacotes
  registrar controle_bytes "$r" "$b" bytes
  tp=$((tp + p)); tb=$((tb + b))
  ex "$r" cp /tmp/regime.pcap "/resultados/$DIR/regime-$r.pcap"
done
registrar controle_pacotes total "$tp" pacotes
registrar controle_bytes total "$tb" bytes
registrar controle_taxa total "$(awk -v b="$tb" -v j="$JANELA" 'BEGIN { printf "%.1f", b * 8 / j }')" bit/s
registrar controle_pacotes_por_min total "$(awk -v p="$tp" -v j="$JANELA" 'BEGIN { printf "%.1f", p * 60 / j }')" pacotes/min

# 4. Delay e caminho
log "medindo RTT e caminho de ha até he"
ex ha ping -c 20 -i 0.2 10.0.5.10 > "$OUT/ping.txt" 2>&1
rtt=$(grep rtt "$OUT/ping.txt" | awk -F'= ' '{print $2}' | awk -F/ '{print $1, $2, $3}')
set -- $rtt
registrar rtt_min ha-he "${1:-NA}" ms; registrar rtt_medio ha-he "${2:-NA}" ms; registrar rtt_max ha-he "${3:-NA}" ms
ex ha traceroute -n -w 1 -q 1 10.0.5.10 > "$OUT/caminho.txt" 2>&1
# Saltos só contam se o traceroute chegou a he; senão o número de linhas é só o limite (30).
registrar saltos ha-he "$(awk '$2 == "10.0.5.10" { n = $1 } END { print n ? n : "NA" }' "$OUT/caminho.txt")" saltos

# 5. Falha do enlace A-sw1
log "cenário de falha: ping contínuo por ${FALHA_TOTAL}s, enlace cai após ${FALHA_APOS}s"
# O ping do iputils encerra ao receber um ICMP de erro (ex.: Destination Net Unreachable),
# então ele é reiniciado até completar FALHA_TOTAL segundos.
docker compose exec -d ha sh -c "fim=\$((\$(date +%s) + $FALHA_TOTAL)); : > /resultados/$DIR/falha-ping.txt;
  while [ \$(date +%s) -lt \$fim ]; do
    ping -D -i 0.2 -W 1 -w \$((fim - \$(date +%s))) 10.0.5.10 >> /resultados/$DIR/falha-ping.txt 2>&1
  done"
for r in $ROTEADORES; do
  docker compose exec -d "$r" sh -c "timeout $FALHA_TOTAL tcpdump -i any -Q out -nn -w /tmp/falha.pcap '$FILTRO' 2>/dev/null"
done
sleep "$FALHA_APOS"
scripts/falha.sh down a 10.0.20. >/dev/null
log "enlace A-sw1 derrubado"
sleep $((FALHA_TOTAL - FALHA_APOS + 3))
scripts/falha.sh up a 10.0.20. >/dev/null
log "enlace A-sw1 restaurado"

# Maior intervalo entre respostas consecutivas, menos o intervalo normal de 0,2 s.
indisp=$(grep 'bytes from' "$OUT/falha-ping.txt" | sed 's/^\[\([0-9.]*\)\].*/\1/' |
  awk 'NR > 1 { g = $1 - ant; if (g > m) m = g } { ant = $1 } END { v = m - 0.2; if (v < 0) v = 0; printf "%.1f", v }')
# Soma de todas as execuções do ping (uma por reinício).
enviados=$(grep 'packets transmitted' "$OUT/falha-ping.txt" | awk '{ s += $1 } END { print s + 0 }')
recebidos=$(grep 'packets transmitted' "$OUT/falha-ping.txt" | awk '{ s += $4 } END { print s + 0 }')
registrar falha_indisponibilidade ha-he "$indisp" s
registrar falha_pacotes_perdidos ha-he "$(( ${enviados:-0} - ${recebidos:-0} ))" pacotes
fp=0
for r in $ROTEADORES; do fp=$((fp + $(pacotes_pcap "$r" /tmp/falha.pcap))); done
registrar falha_controle_pacotes total "$fp" pacotes

log "métricas gravadas em $CSV"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
