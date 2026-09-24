"""Constantes de integração com a infraestrutura.

Estes valores são usados fora do pacote (scripts de métricas e de verificação).
Alterar qualquer um deles exige alterar também scripts/lib.sh.
"""

# Porta UDP de TODAS as mensagens de controle do algoritmo, envio e recepção.
# scripts/metricas.sh conta o tráfego de controle com o filtro "udp port 5555".
PORTA_UDP = 5555

# Número de protocolo com que as rotas são instaladas no kernel (ip route ... proto 99).
# scripts/verificar.sh e scripts/metricas.sh contam as rotas aprendidas com
# "ip route show proto 99". Rotas instaladas sem esse número não serão contadas.
PROTO_KERNEL = 99

# Diretório onde o agente grava o log de eventos (ver interfaces.RegistroEventos).
# No container, /resultados é o diretório resultados/ do repositório.
DIR_LOG = "/resultados/proprio"

# Métrica que representa destino inalcançável. O valor é decisão da dupla,
# mas precisa existir para que CalculoRotas possa anunciar rotas removidas.
METRICA_INFINITA = float("inf")
