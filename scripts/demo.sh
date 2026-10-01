#!/bin/sh
# Demonstração para o vídeo: roda OSPF, RIP e o algoritmo próprio (Gravidade) em sequência
# sobre a mesma topologia, sem interação. Basta iniciar e gravar o terminal.
# Toda linha impressa começa com o horário [HH:MM:SS], inclusive a saída dos comandos.
#
# Uso: scripts/demo.sh   (ou make demo PROTOS="ospf rip proprio" ATRASO=0)
# Variáveis (padrão entre parênteses):
#   PROTOS     (ospf rip proprio) protocolos, na ordem em que rodam
#   ATRASO     (0)   1 = cenário com atraso de configs/atrasos.conf, com comparação no final
#   PAUSA      (2)   segundos de pausa entre etapas; 0 para testar rápido
#   FALHA_APOS (10)  segundos de ping antes de derrubar o enlace
#   CONV_MAX   (180) tempo máximo esperando a convergência inicial, em s
#   VOLTA_MAX  (240) tempo máximo esperando o ping voltar depois da falha, em s
#   PING_INT   (0.5) intervalo do ping contínuo, em s
#
# Para cada protocolo: sobe do zero, espera a convergência, mostra vizinhos, rotas e caminho,
# derruba o enlace de A no sw1 com ping contínuo de ha para he e mede quanto tempo o ping
# ficou sem resposta. O enlace é restaurado ao sair, inclusive com Ctrl+C.
set -u
cd "$(dirname "$0")/.."
. scripts/lib.sh

PROTOS="${PROTOS:-ospf rip proprio}"
ATRASO="${ATRASO:-0}"; export ATRASO
PAUSA="${PAUSA:-2}"; FALHA_APOS="${FALHA_APOS:-10}"
CONV_MAX="${CONV_MAX:-180}"; VOLTA_MAX="${VOLTA_MAX:-240}"; PING_INT="${PING_INT:-0.5}"
for p in $PROTOS; do validar_proto "$p"; done
case "$ATRASO" in 0|1) ;; *) echo "ATRASO deve ser 0 ou 1" >&2; exit 1;; esac

ORIGEM=ha; DESTINO=$(ip_host he); PREFIXO_DESTINO=10.0.5.0/24
NO_FALHA=a; REDE_FALHA=10.0.20.
SUFIXO_ATRASO=""; [ "$ATRASO" = 1 ] && SUFIXO_ATRASO=" ATRASO=1"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/demo.XXXXXX")
PID_PING=""; PID_OBS=""; PID_CONT=""; ENLACE_CAIDO=0

# ---------------------------------------------------------------- saída
if [ -t 1 ] && [ "${TERM:-dumb}" != dumb ] && [ -z "${NO_COLOR:-}" ]; then
  ESC=$(printf '\033')
  C0="$ESC[0m"; NEG="$ESC[1m"; DIM="$ESC[2m"
  INV="$ESC[7m"; VERDE="$ESC[1;32m"; VERM="$ESC[1;31m"; AMAR="$ESC[1;33m"; AZUL="$ESC[1;34m"
  CIANO="$ESC[1;36m"; MAG="$ESC[1;35m"
else
  C0=""; NEG=""; DIM=""; INV=""; VERDE=""; VERM=""; AMAR=""; AZUL=""; CIANO=""; MAG=""
fi
LINHA="════════════════════════════════════════════════════════════════════════"

hora() { date +%H:%M:%S; }
diz() { printf '[%s] %s\n' "$(hora)" "$*"; }
# Prefixa cada linha da entrada com o horário e o texto em $1.
carimbo() { while IFS= read -r l || [ -n "$l" ]; do printf '[%s] %s%s\n' "$(hora)" "${1:-}" "$l"; done; }
roda() { "$@" 2>&1 | carimbo "  "; }
pausa() { case "$PAUSA" in 0|0.0|"") ;; *) sleep "$PAUSA";; esac; }

cor_proto() { case "$1" in ospf) printf '%s' "$CIANO";; rip) printf '%s' "$AMAR";;
                           proprio) printf '%s' "$MAG";; *) printf '%s' "$AZUL";; esac; }
nome_proto() { case "$1" in ospf) echo OSPF;; rip) echo RIP;; proprio) echo GRAVIDADE;;
                            *) printf '%s\n' "$1" | tr a-z A-Z;; esac; }

# Cabeçalho de etapa: $1 protocolo (ou rótulo), $2 o que vai acontecer, $3 comando equivalente.
cabecalho() {
  c=$(cor_proto "$1")
  diz ""
  printf '[%s] %s%s%s\n' "$(hora)" "$c" "$LINHA" "$C0"
  printf '[%s] %s %s %s  %s%s%s\n' "$(hora)" "$c$INV" "$(nome_proto "$1")" "$C0" "$NEG" "$2" "$C0"
  [ -n "${3:-}" ] && printf '[%s]  %s$ %s%s\n' "$(hora)" "$AZUL" "$3" "$C0"
  printf '[%s] %s%s%s\n' "$(hora)" "$c" "$LINHA" "$C0"
  pausa
}
# Subtítulo dentro de uma etapa: $1 descrição, $2 comando equivalente.
subtitulo() {
  diz ""
  printf '[%s] %s▸ %s%s   %s$ %s%s\n' "$(hora)" "$NEG" "$1" "$C0" "$AZUL" "$2" "$C0"
}

# Funções awk que dão nome aos endereços da topologia (10.0.20.5 -> E, 10.0.5.10 -> he).
AWK_NOMES='
function letra(n) { return substr("ABCDE", n, 1) }
function nome(ip,   o) {
  split(ip, o, ".")
  if (o[3] >= 1 && o[3] <= 5) return o[4] == 10 ? "h" tolower(letra(o[3])) : letra(o[3])
  return letra(o[4])
}
function rede(ip,   o) {
  split(ip, o, ".")
  if (o[3] >= 1 && o[3] <= 5) return "LAN " letra(o[3])
  return o[3] == 10 ? "sw0" : o[3] == 20 ? "sw1" : o[3] == 25 ? "be" : o[3] == 34 ? "cd" : "?"
}'

# Traceroute com o nome de cada salto; grava a saída bruta em $1.
traceroute_anotado() {
  ex "$ORIGEM" traceroute -n -w 1 -q 1 "$DESTINO" > "$1" 2>&1
  awk "$AWK_NOMES"' $2 ~ /^10\./ { printf "%-32s <- %s\n", $0, nome($2); next } { print }' "$1" | carimbo "  "
}
# Logo depois de uma mudança de rota um salto pode não responder; tenta de novo uma vez.
traceroute_estavel() {
  for tentativa in 1 2; do
    traceroute_anotado "$1"
    case "$(caminho "$1")" in *\?*|"sem caminho") ;; *) return;; esac
    [ "$tentativa" = 2 ] && return
    diz "${AMAR}traceroute incompleto (salto sem resposta); repetindo em 3 s$C0"
    sleep 3
  done
}
# Caminho resumido a partir da saída do traceroute: ha -> A -> B -> E -> he
caminho() {
  awk "$AWK_NOMES"' $2 ~ /^10\./ { s = s " -> " nome($2); if ($2 == "'"$DESTINO"'") ok = 1 }
    $2 == "*" { s = s " -> ?" } END { print ok ? "'"$ORIGEM"'" s : "sem caminho" }' "$1"
}

# ---------------------------------------------------------------- processos em segundo plano
# Ping contínuo de ha para he. A saída bruta (com o horário do -D) vai para $TMP/ping.raw,
# que é usado para medir a indisponibilidade; na tela cada linha leva o horário local.
iniciar_ping() {
  : > "$TMP/ping.raw"
  ( ex "$ORIGEM" ping -D -O -i "$PING_INT" -W 1 "$DESTINO" 2>&1 | while IFS= read -r l; do
      printf '%s\n' "$l" >> "$TMP/ping.raw"
      case "$l" in \[*\]*) l=${l#*] };; esac
      printf '[%s] %sping │%s %s\n' "$(hora)" "$DIM" "$C0" "$l"
    done ) &
  PID_PING=$!
}

# Imprime a rota de A para a LAN de he sempre que o próximo salto ou a interface mudam
# (mudança só de métrica não conta, como no evento rota_instalada do algoritmo próprio).
iniciar_observador() {
  rm -f "$TMP/parar"
  ( ant=""
    while [ ! -f "$TMP/parar" ]; do
      r=$(ex "$NO_FALHA" ip route show "$PREFIXO_DESTINO" 2>/dev/null | head -n 1)
      chave=$(printf '%s\n' "$r" | awk '{ for (i = 1; i < NF; i++) if ($i == "via" || $i == "dev") printf "%s %s ", $i, $(i + 1) }')
      [ -n "$chave" ] || chave="sem rota"
      if [ "$chave" != "$ant" ]; then
        txt=$(printf '%s\n' "$r" | awk "$AWK_NOMES"' NF == 0 { print "sem rota (o ping não tem por onde sair de A)"; exit }
          { sub(/^[^ ]+ /, ""); s = $0
            for (i = 1; i < NF; i++) if ($i == "via") s = s "  => próximo salto " nome($(i + 1)) ", pela " rede($(i + 1))
            print s }')
        if [ -z "$ant" ]; then rotulo="rota atual"; else rotulo="ROTA MUDOU"; fi
        printf '[%s] %srota │ %s  A -> %s: %s%s\n' "$(hora)" "$VERDE" "$rotulo" "$PREFIXO_DESTINO" "$txt" "$C0"
        ant=$chave
      fi
      sleep 0.5
    done ) &
  PID_OBS=$!
}

# Contador: a cada 5 s imprime "$1 N s" seguido do conteúdo de $TMP/estado.
iniciar_contador() {
  : > "$TMP/estado"
  ( n=0; while :; do sleep 5; n=$((n + 5)); diz "${AMAR}aguardando · $1${n} s$C0 $(cat "$TMP/estado" 2>/dev/null)"; done ) &
  PID_CONT=$!
}
parar_contador() {
  [ -n "$PID_CONT" ] && { kill "$PID_CONT" 2>/dev/null; wait "$PID_CONT" 2>/dev/null; PID_CONT=""; }
}

parar_fundo() {
  parar_contador
  : > "$TMP/parar" 2>/dev/null
  if [ -n "$PID_PING" ]; then
    ex "$ORIGEM" pkill -x ping >/dev/null 2>&1
    kill "$PID_PING" 2>/dev/null; wait "$PID_PING" 2>/dev/null; PID_PING=""
  fi
  if [ -n "$PID_OBS" ]; then
    wait "$PID_OBS" 2>/dev/null; PID_OBS=""
  fi
}

limpar() {
  trap - EXIT INT TERM
  parar_fundo
  if [ "$ENLACE_CAIDO" = 1 ]; then
    sh scripts/falha.sh up "$NO_FALHA" "$REDE_FALHA" >/dev/null 2>&1 && diz "limpeza: enlace de A no sw1 restaurado"
    ENLACE_CAIDO=0
  fi
  rm -rf "$TMP"
}
trap limpar EXIT
trap 'diz "interrompido"; exit 130' INT TERM

# ---------------------------------------------------------------- medições
# Primeira resposta do ping depois do instante $1 (relógio do -D); vazio se não houve.
primeira_resposta_apos() {
  awk -v q="$1" '/bytes from/ && !/DUP/ { t = substr($1, 2) + 0; if (t > q) { printf "%.6f\n", t; exit } }' "$TMP/ping.raw"
}
# Analisa o ping em torno da queda no instante $1. Imprime "indisp perdidos perdidos_antes":
#   indisp         intervalo entre a última resposta antes da queda e a primeira depois, menos o
#                  intervalo do ping (como em metricas.sh); se não houve resposta antes da queda,
#                  conta da queda até a primeira resposta; NA se o ping não voltou
#   perdidos       pacotes sem resposta desde o primeiro enviado (icmp_seq=1)
#   perdidos_antes desses, os que ficaram sem resposta antes da queda
analisar_ping() {
  awk -v q="$1" -v iv="$PING_INT" '
    function seq(   r) { match($0, /icmp_seq=[0-9]+/); return substr($0, RSTART + 9, RLENGTH - 9) + 0 }
    { t = substr($1, 2) + 0 }
    /bytes from/ && !/DUP/ {
      s = seq(); if (!(s in ok)) { ok[s] = 1; rec++ }; if (s > ult) ult = s
      if (t <= q) { tb = t; nb++ } else if (ta == "") ta = t
    }
    /no answer yet/ && t <= q { pend[seq()] = 1 }
    END {
      if (ta == "") g = "NA"
      else { g = nb ? ta - tb - iv : ta - q; if (g < 0) g = 0; g = sprintf("%.1f", g) }
      for (s in pend) if (!(s in ok)) antes++
      printf "%s %d %d\n", g, ult - rec, antes
    }' "$TMP/ping.raw"
}
# Horário com milissegundos e o instante em segundos: "HH:MM:SS.mmm 1790889742.123"
instante() {
  python3 -c 'import time; t = time.time(); print("%s.%03d %.3f" % (time.strftime("%H:%M:%S", time.localtime(t)), int(t % 1 * 1000), t))' 2>/dev/null ||
    echo "$(hora) $(date +%s)"
}
rtt_medio() {
  ex "$ORIGEM" ping -q -c 10 -i 0.2 -W 1 "$DESTINO" 2>&1 | awk -F/ '/^rtt/ { print $5 }'
}

# ---------------------------------------------------------------- etapas
subir() {
  diz "derrubando o laboratório anterior"
  docker compose down --remove-orphans -t 1 > "$TMP/compose.log" 2>&1
  diz "subindo roteadores e hosts com PROTO=$1$SUFIXO_ATRASO (saída do docker compose omitida)"
  if ! PROTO="$1" docker compose up -d --build >> "$TMP/compose.log" 2>&1; then
    diz "${VERM}falha ao subir o laboratório; final da saída do docker compose:$C0"
    tail -n 20 "$TMP/compose.log" | carimbo "  "
    exit 1
  fi
  diz "no ar: $(docker compose ps -q | wc -l | tr -d ' ') containers (roteadores a..e, hosts ha..he)"
  if [ "$ATRASO" = 1 ]; then
    sleep 1
    docker compose logs --no-log-prefix "$NO_FALHA" 2>/dev/null | grep atraso | carimbo "  "
  fi
}

esperar_convergencia() {
  inicio=$(date +%s)
  iniciar_contador ""
  while :; do
    t=$(( $(date +%s) - inicio ))
    if [ "$t" -ge "$CONV_MAX" ]; then parar_contador; T_CONV=NA; return 1; fi
    completo=1; est=""
    for r in $ROTEADORES; do
      n=$(redes_na_tabela "$r" 2>/dev/null | tr -d '\r'); n=${n:-0}
      est="$est $(printf %s "$r" | tr a-e A-E)=$n/$N_REDES"
      [ "$n" -eq "$N_REDES" ] || completo=0
    done
    if [ $completo -eq 1 ] && ex "$ORIGEM" ping -c 1 -W 1 "$DESTINO" >/dev/null 2>&1; then
      parar_contador; T_CONV=$(( $(date +%s) - inicio )); return 0
    fi
    [ $completo -eq 1 ] && est="$est  (tabelas completas; ha ainda não alcança he)"
    echo " redes conhecidas:$est" > "$TMP/estado"
    sleep 1
  done
}

mostrar_vizinhos() {
  case "$1" in
    ospf)
      subtitulo "vizinhos OSPF de A" "make vizinhos NO=a PROTO=ospf"
      roda ex a vtysh -c "show ip ospf neighbor" ;;
    rip)
      subtitulo "vizinhos RIP de A (de quem A recebe anúncios)" "docker compose exec a vtysh -c \"show ip rip status\""
      ex a vtysh -c "show ip rip status" 2>&1 | awk '/Routing Information Sources/ { p = 1 } p' | carimbo "  " ;;
    proprio)
      subtitulo "vizinhos do Gravidade em A (eventos vizinho_up do log)" "grep vizinho_up resultados/proprio/a.jsonl"
      log=resultados/proprio/a.jsonl
      ini=$(grep -n '"evento": "inicio"' "$log" 2>/dev/null | tail -n 1 | cut -d: -f1)
      # Só os eventos desta execução (o log acumula execuções), com o tempo desde o início do agente.
      tail -n +"${ini:-1}" "$log" | awk "$AWK_NOMES"'
        function campo(k,   r) {
          if (!match($0, "\"" k "\": \"?[^,\"}]*")) return ""
          r = substr($0, RSTART, RLENGTH); sub(/^"[^"]*": "?/, "", r); return r
        }
        NR == 1 { t0 = campo("t") }
        /"evento": "vizinho_up"/ {
          v = campo("vizinho")
          printf "+%5.1f s  vizinho_up  %s %-10s %s (%s)  rtt %s ms  custo %s\n", campo("t") - t0,
            nome(v), v, rede(v), campo("interface"), campo("rtt_ms"), campo("custo")
        }' | carimbo "  " ;;
  esac
}

demo_protocolo() {
  p=$1; P=$(nome_proto "$p"); t_inicio_proto=$(date +%s)

  cabecalho "$p" "etapa 1/8 · subir o laboratório do zero com $P" "make up PROTO=$p$SUFIXO_ATRASO"
  subir "$p"

  cabecalho "$p" "etapa 2/8 · esperar a convergência (5 roteadores com as $N_REDES redes e ha alcançando he)" \
    "make status   (repita até as $N_REDES redes aparecerem em todos)"
  if esperar_convergencia; then
    diz "${VERDE}✔ $P convergiu em ${T_CONV} s$C0"
  else
    diz "${VERM}✘ $P não convergiu em ${CONV_MAX} s; pulando para o próximo protocolo$C0"
    echo "$p|NA|NA|NA|NA|-|$(( $(date +%s) - t_inicio_proto ))" >> "$TMP/resumo"
    return
  fi

  cabecalho "$p" "etapa 3/8 · vizinhos, tabela de rotas de A e caminho de ha até he" "make vizinhos NO=a PROTO=$p"
  mostrar_vizinhos "$p"
  subtitulo "tabela de rotas de A" "make rotas NO=a"
  roda ex a ip route
  [ "$p" = proprio ] && diz "(as rotas do Gravidade usam proto 99, que o iproute2 exibe com o nome \"openr\")"
  subtitulo "caminho de ha até he" "make trace DE=ha PARA=$DESTINO"
  traceroute_estavel "$TMP/trace-$p-antes.txt"
  caminho_antes=$(caminho "$TMP/trace-$p-antes.txt")
  rtt=$(rtt_medio); rtt=${rtt:-NA}
  diz "caminho: $caminho_antes   RTT médio (10 pings): $rtt ms"
  if [ "$ATRASO" = 1 ]; then
    { echo "$P"; echo "caminho: $caminho_antes"; echo "RTT: $rtt ms"
      awk "$AWK_NOMES"' $2 ~ /^10\./ { printf "%2s %-10s %-2s %s\n", $1, $2, nome($2), $3 " " $4 }' "$TMP/trace-$p-antes.txt"
    } > "$TMP/compara-$p.txt"
  fi
  pausa

  cabecalho "$p" "etapa 4/8 · ping contínuo de ha para he e observador da rota de A para $PREFIXO_DESTINO" \
    "docker compose exec ha ping -O $DESTINO   e   make rotas NO=a"
  iniciar_observador
  iniciar_ping
  diz "o enlace de A no sw1 cai em ${FALHA_APOS} s"
  sleep "$FALHA_APOS"

  cabecalho "$p" "etapa 5/8 · derrubar o enlace de A no sw1 ($REDE_FALHA*), como arrancar o cabo" \
    "make falha NO=a REDE=$REDE_FALHA"
  ENLACE_CAIDO=1
  sh scripts/falha.sh down "$NO_FALHA" "$REDE_FALHA" 2>&1 | carimbo "  "
  set -- $(instante); hora_queda=$1; t_queda=$2; inicio=$(date +%s)
  diz "${VERM}✘ ENLACE DERRUBADO às $hora_queda$C0"

  cabecalho "$p" "etapa 6/8 · esperar o ping voltar a responder (limite de ${VOLTA_MAX} s)" \
    "(acompanhe o ping da etapa 4)"
  t_volta=""
  iniciar_contador "sem resposta há "
  while :; do
    t_volta=$(primeira_resposta_apos "$t_queda")
    [ -n "$t_volta" ] && break
    [ $(( $(date +%s) - inicio )) -ge "$VOLTA_MAX" ] && break
    sleep 0.5
  done
  parar_contador
  set -- $(analisar_ping "$t_queda"); indisp=$1; perdidos=$(( $2 - $3 )); antes=$3
  if [ -n "$t_volta" ]; then
    ate=$(awk -v a="$t_volta" -v b="$t_queda" 'BEGIN { printf "%.1f", a - b }')
    diz "${VERDE}✔ o ping voltou ${ate} s depois da queda$C0"
    diz "${NEG}tempo sem resposta: ${indisp} s · pacotes perdidos na falha: ${perdidos}$C0"
  else
    diz "${VERM}✘ o ping não voltou em ${VOLTA_MAX} s · pacotes perdidos: ${perdidos}$C0"
  fi
  if [ "$antes" -gt 0 ]; then
    diz "${AMAR}atenção: ${antes} pacote(s) já tinham ficado sem resposta antes da queda do enlace$C0"
  fi
  pausa

  cabecalho "$p" "etapa 7/8 · caminho de ha até he depois da falha" "make trace DE=ha PARA=$DESTINO"
  traceroute_estavel "$TMP/trace-$p-depois.txt"
  caminho_depois=$(caminho "$TMP/trace-$p-depois.txt")
  diz "caminho antes:  $caminho_antes"
  diz "caminho depois: $caminho_depois"
  pausa

  cabecalho "$p" "etapa 8/8 · restaurar o enlace e encerrar o ping e o observador" "make restaura NO=a REDE=$REDE_FALHA"
  sh scripts/falha.sh up "$NO_FALHA" "$REDE_FALHA" 2>&1 | carimbo "  "
  ENLACE_CAIDO=0
  pausa
  parar_fundo
  dur=$(( $(date +%s) - t_inicio_proto ))
  [ -n "$t_volta" ] || indisp=">$VOLTA_MAX"
  [ "$antes" -gt 0 ] && perdidos="$perdidos (+$antes antes)"
  echo "$p|$T_CONV|$indisp|$perdidos|$rtt|$caminho_depois|$dur" >> "$TMP/resumo"
  diz "$(cor_proto "$p")RESUMO $P: convergência ${T_CONV} s · ${indisp} s sem resposta · ${perdidos} pacotes perdidos · depois da falha: ${caminho_depois} · etapa levou ${dur} s$C0"
  pausa
}

# Coloca as colunas dos arquivos lado a lado.
lado_a_lado() {
  paste -d '|' "$1" "$2" | while IFS='|' read -r e d; do
    printf '[%s]   %-40s │ %s\n' "$(hora)" "$e" "$d"
  done
}

# ---------------------------------------------------------------- roteiro
t_demo=$(date +%s)
: > "$TMP/resumo"
cabecalho demo "laboratório de roteamento: $(for p in $PROTOS; do printf '%s ' "$(nome_proto "$p")"; done)" \
  "make demo PROTOS=\"$PROTOS\" ATRASO=$ATRASO"
diz "topologia: roteadores A..E, hosts ha..he; ha = $(ip_host ha), he = $DESTINO"
diz "falha: enlace do roteador A na rede 10.0.20.0/24 (sw1); sem ele, de A até E restam os caminhos por B ou por C e D"
if [ "$ATRASO" = 1 ]; then
  diz "cenário com atraso (configs/atrasos.conf): sw0 1 ms, sw1 15 ms, be 3 ms, cd 5 ms (ida)"
fi
pausa

for p in $PROTOS; do demo_protocolo "$p"; done

if [ "$ATRASO" = 1 ]; then
  cabecalho demo "comparação no cenário com atraso: caminho e RTT de ha até he" \
    "make up PROTO=proprio ATRASO=1 ; make trace ; make ping   (idem com PROTO=rip)"
  if [ -f "$TMP/compara-proprio.txt" ] && [ -f "$TMP/compara-rip.txt" ]; then
    lado_a_lado "$TMP/compara-proprio.txt" "$TMP/compara-rip.txt"
    diz ""
    diz "o Gravidade mede o atraso dos enlaces e desvia por B; o RIP conta saltos e vai direto pelo sw1"
  else
    diz "a comparação precisa de proprio e rip em PROTOS; disponível:"
    for f in "$TMP"/compara-*.txt; do [ -f "$f" ] && carimbo "  " < "$f"; done
  fi
  pausa
fi

cabecalho demo "resumo da demonstração$( [ "$ATRASO" = 1 ] && echo ' (cenário com atraso)')" ""
diz "${NEG}protocolo   convergência   sem resposta   perdidos         RTT médio   duração   caminho depois da falha$C0"
while IFS='|' read -r p conv indisp perd rtt cam dur; do
  case "$conv" in NA) ;; *) conv="$conv s";; esac
  case "$indisp" in NA) ;; *) indisp="$indisp s";; esac
  case "$rtt" in NA) ;; *) rtt="$rtt ms";; esac
  printf '[%s] %-11s %-14s %-14s %-16s %-11s %-9s %s\n' "$(hora)" "$(nome_proto "$p")" "$conv" "$indisp" \
    "$perd" "$rtt" "${dur} s" "$cam"
done < "$TMP/resumo"
diz ""
diz "fim da demonstração em $(( $(date +%s) - t_demo )) s. O laboratório continua no ar com o último protocolo (make down para derrubar)."
