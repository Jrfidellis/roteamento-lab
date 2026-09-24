# Roteador: FRRouting + ferramentas de captura e o pacote do algoritmo próprio.
FROM quay.io/frrouting/frr:10.2.1
RUN apk add --no-cache tcpdump iputils
COPY docker/router-entrypoint.sh /usr/local/bin/router-entrypoint.sh
RUN chmod +x /usr/local/bin/router-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/router-entrypoint.sh"]
