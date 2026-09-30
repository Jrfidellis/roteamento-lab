# Algoritmo próprio: Gravidade

## Ideia

Cada enlace é um par de corpos que se atraem. A força entre eles é `F = m / d²`:

- **d (distância)** = RTT (tempo de ida e volta) suavizado entre os dois vizinhos, em ms, com piso de 1 ms.
- **m (massa)** = fração de hellos entregues (`1 - perda`), com mínimo de 0,1.

O custo do enlace é o inverso da força: `custo = 1/F = d² / m`. O custo de um caminho é a **soma** dos custos dos enlaces, e o roteador escolhe o menor.

## Por que d² e não d

- Enlace lento fica quadraticamente mais caro: dois saltos de 10 ms (custo 200) vencem um salto de 20 ms (custo 400). O RIP não enxerga isso (conta saltos) e o OSPF só enxerga a banda configurada, não o atraso medido.
- A soma continua aditiva, então o problema é de caminho mínimo comum: converge e admite prova de ausência de loop. Multiplicar forças ao longo do caminho quebraria isso.
- Perda entra pela massa: um enlace que perde metade dos hellos custa o dobro.

## Tipo: vetor de caminho (path-vector)

Cada rota anunciada carrega a lista de `router_id` que ela atravessa. Quem se encontra na lista descarta o anúncio. Isso elimina a contagem ao infinito sem hold-down (obrigação 6 do contrato). Somam-se:

- **split horizon por interface**: rota aprendida numa interface não é anunciada de volta por ela;
- **estado soft**: cada anúncio substitui a tabela inteira do vizinho, então omitir uma rota é retirá-la;
- **atualização disparada** por mudança, com intervalo mínimo de 0,5 s, além do anúncio periódico.

Loops transitórios de encaminhamento ainda são possíveis em qualquer protocolo distribuído entre a mudança e a propagação dela. As atualizações disparadas encurtam essa janela.

## Vizinhança

- `hello` em broadcast a cada `intervalo_hello_s`; o vizinho responde `eco` em unicast devolvendo o timestamp. O RTT é `agora - ts`, medido só no relógio local, sem sincronizar relógios.
- Um vizinho só sobe depois do primeiro eco, o que prova que o enlace funciona nos dois sentidos.
- Morre após `tempo_morto_s` sem nenhuma mensagem

## Mensagens (UDP 5555, JSON compacto)

| Tipo | Corpo | Envio |
| ---- | ----- | ----- |
| `hello` | `{seq, ts}` | broadcast por interface |
| `eco` | `{seq, ts}` | unicast ao remetente do hello |
| `anuncio` | `{rotas: [{rede, custo, caminho}]}` | broadcast por interface |

## Kernel

Só rotas `proto 99` (o `ip route` mostra esse número como `openr`). A sincronização compara com `ip -j route show proto 99` e só executa `ip` quando há mudança real. O `ip route replace` com métrica diferente cria uma segunda rota em vez de trocar a primeira, então a implementação apaga a antiga logo em seguida.

## Temporizadores (`configs/proprio/*.json`)

| Parâmetro | Valor | Motivo |
| --------- | ----- | ------ |
| `intervalo_hello_s` | 5 s | frequência da medição de RTT e da prova de vida |
| `tempo_morto_s` | 15 s | 3 × hello: tolera a perda de 2 hellos seguidos sem derrubar o vizinho |
| `intervalo_anuncio_s` | 10 s | refresco periódico; mudanças são anunciadas antes, por atualização disparada |

Como o vizinho é declarado morto entre 10 s e 15 s depois do último hello recebido, a reconvergência após uma falha fica nessa faixa mais a propagação.

## Parâmetros internos

| Parâmetro | Valor | Motivo |
| --------- | ----- | ------ |
| `PISO_RTT_MS` | 1,0 | RTT abaixo disso é ruído de agendamento |
| `ALFA_RTT` / `ALFA_PERDA` | 0,3 / 0,2 | suaviza sem atrasar demais a reação |
| `HISTERESE` | 25 % | o custo publicado só muda se variar mais que isso; evita flapping |
| `MASSA_MIN` | 0,1 | custo nunca explode por perda alta |
| `INTERVALO_MIN_DISPARO_S` | 0,5 | limita o tráfego de controle em cascatas de mudança |
| `RESYNC_KERNEL_S` | 5 | corrige o kernel se alguém mexer nele por fora |

## Limitação observada no ambiente de testes

Nos containers, todos os enlaces têm praticamente o mesmo RTT. No roteador A, as rotas aprendidas ficaram com métrica entre 12 e 18 (12 a 13 na primeira, 16 a 18 nas seguintes), ou seja, cada enlace custa cerca de 13,5 (RTT em torno de 3,5 a 4,3 ms, que é ruído do Docker). Como os custos são quase iguais, o algoritmo escolhe caminhos parecidos com os de uma contagem de saltos. A vantagem da métrica só aparece quando os enlaces têm atrasos diferentes. Para demonstrá-la seria preciso configurar atraso nos enlaces (por exemplo com `tc netem`).

## Como usar

```
make up PROTO=proprio        # sobe os 5 roteadores e os 5 hosts com o algoritmo próprio
sleep 30                      # espera a convergência
make verificar PROTO=proprio # confere rotas, pings e o teste de falha
make down                    # derruba tudo
```

Para ver o que um roteador aprendeu:

```
docker compose exec a ip route show proto 99
cat resultados/proprio/a.jsonl
```

O algoritmo está em `algoritmo/implementacao.py`. As interfaces e o contrato estão em `algoritmo/interfaces.py` e `algoritmo/CONTRATO.md`.

## Resultado do teste de aceite (`make verificar PROTO=proprio`)

| Verificação | Resultado |
| ----------- | --------- |
| Cada roteador conhece as 9 redes | 9/9 nos 5 roteadores |
| Rotas aprendidas com proto 99 | 6 em cada roteador |
| Ping entre os 5 hosts | 20 de 20 pares |
| Falha do enlace A–sw1 | `ha` voltou a alcançar `he` em cerca de 13 s (limite: 60 s) |
| Enlace restaurado | conectividade completa |

## Comparação com RIP e OSPF

Preencher **somente** com os números de `resultados/graficos/resumo.md`, depois de rodar `make metricas` e `make graficos` para os três protocolos.

| Métrica | OSPF | RIP | Gravidade |
| ------- | ---- | --- | --------- |
| Convergência inicial (s) | | | 5 |
| Pacotes de controle por minuto | | | 672 |
| Indisponibilidade após a falha (s) | | | 12,7 |
| Pacotes perdidos na falha | | | 64 |

Pontos de discussão, a confirmar contra os números:

- **Tráfego de controle:** o hello com eco a cada vizinho e o anúncio com o caminho completo tendem a gerar mais mensagens que o RIP.
- **Reconvergência:** depende dos temporizadores. Aqui a detecção leva entre 10 s e 15 s.
- **Escalabilidade:** o anúncio carrega o caminho completo, então o tamanho cresce com o número de saltos da rede. O OSPF escala melhor com áreas.