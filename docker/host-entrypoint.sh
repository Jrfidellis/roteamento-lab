#!/bin/sh
# Troca a rota default criada pelo Docker pelo roteador da própria LAN.
set -eu
: "${GATEWAY:?defina GATEWAY}"
ip route replace default via "$GATEWAY"
exec sleep infinity
