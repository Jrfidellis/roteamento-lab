# Laboratório de roteamento: OSPF, RIP e algoritmo próprio sobre a mesma topologia.
# Uso rápido: make up PROTO=ospf ; make verificar PROTO=ospf ; make metricas PROTO=ospf
PROTO ?= ospf
NO    ?= a
DE    ?= ha
PARA  ?= 10.0.5.10
REDE  ?= 10.0.20.
COMPOSE = docker compose

.PHONY: help build up down status rotas vizinhos ping trace falha restaura verificar \
        metricas metricas-todas graficos shell vtysh logs limpar

help:  ## lista os comandos
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

build:  ## constrói as imagens
	$(COMPOSE) build

up:  ## sobe do zero com PROTO=ospf|rip|proprio (derruba o que estiver rodando)
	@case "$(PROTO)" in ospf|rip|proprio) ;; *) echo "PROTO deve ser ospf, rip ou proprio"; exit 1;; esac
	$(COMPOSE) down --remove-orphans
	PROTO=$(PROTO) $(COMPOSE) up -d --build
	@echo "laboratório no ar com $(PROTO). OSPF leva ~50 s para convergir; RIP ~10 s."

down:  ## derruba o laboratório
	$(COMPOSE) down --remove-orphans

status:  ## tabela de rotas de todos os roteadores
	@for r in a b c d e; do echo "== $$r"; $(COMPOSE) exec -T $$r ip route; done

rotas:  ## tabela de rotas de um roteador: make rotas NO=a
	$(COMPOSE) exec -T $(NO) ip route

vizinhos:  ## vizinhos OSPF ou estado RIP do roteador NO
	@case "$(PROTO)" in \
	  ospf) $(COMPOSE) exec -T $(NO) vtysh -c "show ip ospf neighbor";; \
	  rip)  $(COMPOSE) exec -T $(NO) vtysh -c "show ip rip";; \
	  *)    echo "use o log em resultados/proprio/$(NO).jsonl";; esac

ping:  ## ping entre hosts: make ping DE=ha PARA=10.0.5.10
	$(COMPOSE) exec -T $(DE) ping -c 4 $(PARA)

trace:  ## traceroute: make trace DE=ha PARA=10.0.5.10
	$(COMPOSE) exec -T $(DE) traceroute -n -w 1 -q 1 $(PARA)

falha:  ## derruba o enlace de NO na REDE: make falha NO=a REDE=10.0.20.
	sh scripts/falha.sh down $(NO) $(REDE)

restaura:  ## restaura o enlace: make restaura NO=a REDE=10.0.20.
	sh scripts/falha.sh up $(NO) $(REDE)

verificar:  ## critério de aceite (convergência, conectividade, falha): make verificar PROTO=ospf
	sh scripts/verificar.sh $(PROTO)

metricas:  ## coleta as métricas de um protocolo (~7 min): make metricas PROTO=ospf
	sh scripts/metricas.sh $(PROTO)

metricas-todas:  ## coleta OSPF, RIP e algoritmo próprio em sequência
	-sh scripts/metricas.sh ospf
	-sh scripts/metricas.sh rip
	-sh scripts/metricas.sh proprio

graficos:  ## gera resultados/graficos/*.png e resumo.md
	docker build -q -t roteamento-lab/analise -f docker/analise.Dockerfile . >/dev/null
	docker run --rm -v "$(CURDIR)":/lab roteamento-lab/analise

shell:  ## shell em um nó: make shell NO=a
	$(COMPOSE) exec $(NO) sh

vtysh:  ## CLI do FRR (estilo IOS) em um roteador: make vtysh NO=a
	$(COMPOSE) exec $(NO) vtysh

logs:  ## logs de um nó: make logs NO=a
	$(COMPOSE) logs -f $(NO)

limpar:  ## apaga resultados coletados
	rm -rf resultados/ospf resultados/rip resultados/proprio resultados/graficos
