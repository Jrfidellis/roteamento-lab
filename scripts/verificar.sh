#!/bin/sh
# Verifica se o plano de controle em execução convergiu e reage a falha.
# É o critério de aceite do algoritmo próprio e vale igual para OSPF e RIP.
# Uso: scripts/verificar.sh <ospf|rip|proprio>
# LIMITE_S (padrão 60) é o prazo de reconvergência do passo 4. Com os temporizadores
# padrão o RIP leva até ~180 s (timeout da rota de volta em E), então reprova com 60 s.
set -u
cd "$(dirname "$0")/.."
. scripts/lib.sh
PROTO="${1:?uso: verificar.sh <ospf|rip|proprio>}"; validar_proto "$PROTO"
KP=$(proto_kernel "$PROTO")
falhas=0
ok()  { echo "  ok    $*"; }
nok() { echo "  FALHA $*"; falhas=$((falhas + 1)); }

echo "1. Todo roteador conhece as $N_REDES redes"
for r in $ROTEADORES; do
  n=$(redes_na_tabela "$r"); [ "$n" -eq "$N_REDES" ] && ok "$r: $n/$N_REDES" || nok "$r: $n/$N_REDES"
done

echo "2. Rotas não conectadas foram aprendidas pelo protocolo (proto $KP)"
for r in $ROTEADORES; do
  n=$(ex "$r" sh -c "ip route show proto $KP | grep -c '^[0-9]'" | tr -d '\r')
  # Cada roteador tem 3 redes conectadas; as 6 restantes precisam vir do protocolo.
  [ "$n" -eq 6 ] && ok "$r: $n rotas proto $KP" || nok "$r: $n rotas proto $KP (esperado 6)"
done

echo "3. Os 5 hosts se alcançam (20 pares)"
for o in $HOSTS; do for d in $HOSTS; do
  [ "$o" = "$d" ] && continue
  ex "$o" ping -c 1 -W 2 "$(ip_host "$d")" >/dev/null 2>&1 && ok "$o -> $d" || nok "$o -> $d"
done; done

LIMITE_S="${LIMITE_S:-60}"
echo "4. Falha do enlace A-sw1: ha volta a alcançar he em até ${LIMITE_S} s"
scripts/falha.sh down a 10.0.20. >/dev/null
t=0; ate=$LIMITE_S; voltou=0; inicio=$(date +%s)
while [ $t -lt $ate ]; do
  ex ha ping -c 1 -W 1 10.0.5.10 >/dev/null 2>&1 && { voltou=1; break; }
  sleep 1; t=$(( $(date +%s) - inicio ))
done
[ $voltou -eq 1 ] && ok "reconvergiu em ~${t}s" || nok "sem conectividade após ${ate}s"

echo "5. Enlace restaurado: conectividade completa"
scripts/falha.sh up a 10.0.20. >/dev/null
sleep 5
ex ha ping -c 2 -W 2 10.0.5.10 >/dev/null 2>&1 && ok "ha -> he" || nok "ha -> he"

echo
[ $falhas -eq 0 ] && { echo "RESULTADO: $PROTO aprovado"; exit 0; } || { echo "RESULTADO: $PROTO com $falhas falha(s)"; exit 1; }
