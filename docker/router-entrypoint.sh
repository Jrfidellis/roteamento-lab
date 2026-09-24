#!/bin/sh
# Sobe o plano de controle escolhido em PROTO (ospf | rip | proprio) no roteador NODE.
# As configurações vêm de /config (repositório montado só leitura) e são copiadas
# para /etc/frr, para que o FRR nunca escreva de volta no repositório.
set -eu
: "${PROTO:?defina PROTO}" "${NODE:?defina NODE}"

# Remove a rota default criada pelo Docker: o roteador só deve conhecer
# as redes conectadas e o que o protocolo de roteamento aprender.
ip route del default 2>/dev/null || true

case "$PROTO" in
  ospf|rip)
    cp "/config/$PROTO/daemons"      /etc/frr/daemons
    cp "/config/$PROTO/$NODE.conf"   /etc/frr/frr.conf
    cp "/config/vtysh.conf"          /etc/frr/vtysh.conf
    chown -R frr:frr /etc/frr
    echo "[$NODE] iniciando FRR com $PROTO"
    exec /usr/lib/frr/docker-start
    ;;
  proprio)
    echo "[$NODE] iniciando algoritmo próprio"
    cd /opt
    # Se o agente terminar (ou ainda não estiver implementado), o container
    # continua de pé para depuração: docker compose exec <no> sh
    python3 -m algoritmo --config "/config/proprio/$NODE.json" || \
      echo "[$NODE] agente encerrou com código $?"
    exec sleep infinity
    ;;
  *)
    echo "PROTO inválido: $PROTO (use ospf, rip ou proprio)" >&2
    exit 1
    ;;
esac
