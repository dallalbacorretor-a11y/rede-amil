# Rede credenciada Amil — Paraná, Santa Catarina e São Paulo

Consulta da rede credenciada Amil em um único link: escolha o estado, marque os
produtos, filtre por cidade, categoria, especialidade ou bairro, e gere um PDF
de apresentação.

| | Paraná | Santa Catarina | São Paulo |
|---|---|---|---|
| Prestadores | 1.360 | 381 | 4.572 |
| Cidades | 74 | 43 | 57 |
| Hospitais | 111 | 39 | 174 |
| Produtos | 11 | 8 | 9 |
| Praças consultadas | 71 | 39 | 44 |

Levantamento feito na busca avançada do portal da Amil, produto por produto,
praça por praça e tipo de serviço por tipo de serviço (a lista de tipos vem do
próprio portal: consultórios, hospitais, laboratórios, pronto-socorro, pronto
atendimento, hemodiálise, TEA, telemedicina, vacinação, rede preferencial),
conferido por uma busca sem tipo de serviço em cada produto e praça.

## Como atualizar

    python3 ferramentas/coletar.py PR SC SP   # a busca avançada (umas 3 horas)
    python3 ferramentas/montar.py             # a página, a partir da coleta

A coleta fica em `ferramentas/amil/` (uma unidade por credenciado e endereço,
com os produtos de cada praça). A página sai dela, e o comparativo do site
[rede-amil-bradesco](https://dallalbacorretor-a11y.github.io/rede-amil-bradesco/)
usa a mesma coleta, que ele traz daqui na sincronização: atualizou aqui,
atualiza lá.

## Aviso importante

A rede credenciada é definida e alterada exclusivamente pela operadora. Esta
página é um retrato da consulta feita na data indicada no topo dela.
**Confirme no portal da Amil antes de contratar.**

## Contato

Alan Vinicius Dall Alba — Mazza Broker
alan.vinicius@mazzabroker.com.br
