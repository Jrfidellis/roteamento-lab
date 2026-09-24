# Host de acesso (um por LAN): só gera e mede tráfego.
FROM alpine:3.20
RUN apk add --no-cache iproute2 iputils tcpdump iperf3
COPY docker/host-entrypoint.sh /usr/local/bin/host-entrypoint.sh
RUN chmod +x /usr/local/bin/host-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/host-entrypoint.sh"]
