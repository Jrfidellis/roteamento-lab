# Contrato do algoritmo próprio

Este diretório contém só as interfaces. A lógica é da dupla. O que está aqui é o acordo
entre quem implementa o algoritmo e quem mantém a infraestrutura, as métricas e os gráficos:
enquanto os itens abaixo forem respeitados, as duas partes trabalham em paralelo sem se bloquear.

## O que a infraestrutura garante

- Com `make up PROTO=proprio`, cada roteador executa `python3 -m algoritmo --config /config/proprio/<no>.json`,
  com o diretório `algoritmo/` montado em `/opt/algoritmo`. Não é preciso reconstruir a imagem ao editar o código.
- O FRR não roda nesse modo. O kernel só tem as rotas conectadas, sem rota default.
- `net.ipv4.ip_forward=1`, `rp_filter=0` e capacidades `NET_ADMIN` e `NET_RAW` estão ativos.
- Python da imagem: 3.12, só biblioteca padrão. `ip` (iproute2 6.9) e `tcpdump` estão instalados.
- `/resultados` no container é o diretório `resultados/` do repositório.
- Se o agente terminar com erro, o container continua de pé para depuração:
  `make shell NO=a` e depois `cd /opt && python3 -m algoritmo --config /config/proprio/a.json`.

## O que o algoritmo precisa garantir

| # | Obrigação | Por quê | Onde está definido |
| - | --------- | ------- | ------------------ |
| 1 | Toda mensagem de controle usa UDP na porta 5555 | as métricas contam o tráfego com `udp port 5555` | `constantes.PORTA_UDP` |
| 2 | Rotas instaladas com `proto 99` | verificação e métricas contam com `ip route show proto 99` | `constantes.PROTO_KERNEL` |
| 3 | Nunca alterar rotas `proto kernel` (conectadas) | quebraria a própria LAN do roteador | `TabelaKernel` |
| 4 | Remover as rotas `proto 99` ao receber SIGTERM | `make down` / `make up` precisam começar do zero | `Agente.executar` |
| 5 | Detectar vizinho caído em até `tempo_morto_s` e reconvergir | é o cenário de falha das métricas | `Vizinhanca.expirar` |
| 6 | Não formar loops, em regime e durante a reconvergência | pacotes em loop invalidam delay e perda | `CalculoRotas` |
| 7 | Log em `/resultados/proprio/<no>.jsonl` com os eventos obrigatórios | análise e vídeo | `RegistroEventos` |

## Critério de aceite

O algoritmo está pronto quando `make verificar PROTO=proprio` passa. O script é o mesmo usado para
OSPF e RIP e confere:

1. todo roteador tem rota para as 9 redes da topologia;
2. as rotas não conectadas estão com `proto 99`;
3. os 5 hosts se alcançam por ping, nos 20 pares;
4. depois de derrubar o enlace de A em `sw1`, `ha` volta a alcançar `he` em até 60 s;
5. restaurado o enlace, a conectividade continua completa.

## Decisões que ficam com a dupla

Justificar cada uma no README e na apresentação:

- **Critério de custo** (`Metrica`): o que torna um caminho melhor que outro. Exemplos: atraso medido
  entre vizinhos, perda de hellos, carga do enlace, combinação ponderada.
- **Tipo de algoritmo** (`CalculoRotas`): vetor de distância, estado de enlace ou outro.
- **Formato das mensagens** (`Codec`, `Mensagem.tipo`, `Mensagem.corpo`).
- **Descoberta de vizinhos** (`Transporte`): broadcast, multicast ou lista fixa.
- **Proteção contra loops e contagem ao infinito**: split horizon, poison reverse, hold-down, números de sequência.
- **Temporizadores**: os valores em `configs/proprio/*.json` podem ser ajustados; registre o motivo.

## Estrutura

| Arquivo | Conteúdo |
| ------- | -------- |
| `constantes.py` | porta, número de protocolo, diretório de log, métrica infinita |
| `tipos.py` | `Interface`, `Vizinho`, `Rota`, `Mensagem` |
| `config.py` | formato de `configs/proprio/<no>.json` (única parte concreta, para validar o arquivo) |
| `interfaces.py` | `Codec`, `Transporte`, `Metrica`, `Vizinhanca`, `CalculoRotas`, `TabelaKernel`, `RegistroEventos`, `Agente`, `criar_agente()` |
| `__main__.py` | ponto de entrada; sai com código 2 enquanto `criar_agente()` não estiver implementado |
