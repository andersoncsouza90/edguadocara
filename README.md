# Radar de Concursos — Fiscal · Controle · Policial

Monitora **atos oficiais** (DOU e diários municipais) e consolida cada concurso
numa linha do tempo: **previsto → solicitado → autorizado → comissão formada →
banca definida → banca contratada → edital publicado → homologado**.

O site é estático (GitHub Pages, pasta `docs/`) e tem filtros por área, fase,
esfera, UF e busca por órgão, cargo ou banca. Também gera `feed.xml` (RSS) e
`concursos.json`.

## Por que fontes primárias, e não copiar agregadores

| Fundamento | O que diz | Consequência para o projeto |
|---|---|---|
| Lei 9.610/1998, art. 8º, IV | Leis, decretos, regulamentos e "demais atos oficiais" **não** são protegidos por direito autoral | Podemos reproduzir e reorganizar atos publicados em diário oficial |
| Lei 9.610/1998, art. 7º, XIII | Bases de dados com seleção e organização próprias **são** protegidas | Não dá para raspar e republicar a base de PCI Concursos ou Concursos no Brasil |
| CF/88, art. 37, II | A investidura em cargo efetivo depende de aprovação prévia em concurso público | Todo concurso deixa rastro em ato oficial, e é isso que monitoramos |

## Como cada fase é detectada

| Fase | Ato que a comprova | Exemplo de onde sai |
|---|---|---|
| Previsto | PLOA/LOA (Anexo V), plano anual, declaração oficial | **Curadoria manual** (`data/acompanhamento_manual.json`) |
| Solicitado | Pedido de autorização ao órgão central (ex.: MGI) | Curadoria manual (raramente sai em diário) |
| Autorizado | Portaria que autoriza o concurso (federal: Decreto 9.739/2019, autorização do ministro da gestão) | DOU, seção 1 |
| Comissão formada | Portaria que institui a comissão organizadora | DOU seção 1/2, diários estaduais |
| Banca definida | Dispensa ou contratação direta ratificada (em regra, Lei 14.133/2021, art. 75, XV) | DOU seção 3 |
| Banca contratada | Extrato de contrato com a banca | DOU seção 3 |
| Edital publicado | Edital de abertura (ou a retificação dele) | DOU seção 3 |
| Homologado | Homologação do resultado final. A partir dela corre a validade de até 2 anos, prorrogável uma vez (CF, art. 37, III) | DOU |

Cancelamentos e suspensões aparecem como **situação** do concurso. O status
consolidado é sempre o mais avançado entre os atos encontrados, e ele nunca
regride. O histórico completo fica na linha do tempo, com o link de cada ato.

Para o candidato, o site agrupa os concursos em **Abertos / em breve**
(inscrições a abrir ou abertas), **Anunciados** (comissão ou banca),
**Autorizados**, **Previstos**, **Em andamento** e **Encerrados**.

## Fontes

| Fonte | Cobertura | Módulo |
|---|---|---|
| Diário Oficial da União, página "Leitura do Jornal" (seções 1, 2 e 3) | Órgãos federais (RFB, PF, PRF, TCU, CGU, MTE...) e alguns atos estaduais | `radar/fontes/dou.py` |
| [Querido Diário](https://queridodiario.ok.org.br) (API pública) | Diários municipais (auditor fiscal, fiscal de tributos, controladorias) | `radar/fontes/querido_diario.py` |
| Curadoria | Fases "previsto" e "solicitado", com link da fonte | `radar/fontes/manual.py` |

## Estrutura

```
radar/
  classificador.py   # é concurso? área, órgão, fase, banca, vagas, salário, inscrições
  base.py            # base JSON + agrupamento em ciclos + consolidação de status
  fontes/            # coletores (DOU, Querido Diário, curadoria manual)
  site.py            # gera docs/index.html, concursos.json e feed.xml
  modelo_site.html   # front-end (HTML/CSS/JS puro, sem dependências)
data/radar.json      # base versionada no git (cada ato com link da fonte)
tests/               # testes com atos fictícios no formato real
```

Não há dependências externas, só a biblioteca padrão do Python 3.10+.

## Uso

```bash
python -m radar coletar --dias 7
```

```bash
python -m radar listar --area fiscal --grupo anunciados
```

```bash
python -m radar site
```

```bash
python -m unittest discover -s tests
```

Para testar o classificador com um ato colado (a primeira linha é o título):

```bash
python -m radar classificar ato.txt
```

### Curadoria manual

Em `data/acompanhamento_manual.json`, inclua um objeto por ato, sempre com a
URL da fonte:

```json
[
  {
    "orgao": "Receita Federal do Brasil", "sigla": "RFB", "area": "fiscal",
    "esfera": "federal", "tipo": "solicitacao", "data": "2026-10-15",
    "titulo": "Receita envia ao MGI pedido de novo concurso",
    "url": "https://link-da-fonte-oficial", "fonte": "Ofício nº ...",
    "vagas": 100, "observacao": "Pedido citado em ofício"
  }
]
```

Valores aceitos em `tipo`: `previsao`, `solicitacao`, `autorizacao`,
`comissao`, `banca_definida`, `contrato_banca`, `edital_abertura`,
`retificacao`, `suspensao`, `cancelamento`, `resultado`, `homologacao`.

## Automação (GitHub Actions + Pages)

O workflow `.github/workflows/radar.yml` roda todo dia às 06:17 (Brasília).
Ele executa os testes, coleta os últimos 3 dias, gera o site e faz commit de
`data/` e `docs/`. Também dá para rodar manualmente em *Actions → Run workflow*.

Para publicar o site: *Settings → Pages → Deploy from a branch →* escolha a
branch e a pasta `/docs`.

## Limitações conhecidas e próximos passos

1. **Diários estaduais (DOEs).** Cada estado tem um portal diferente, e é lá
   que saem SEFAZ, PC, PM e TCE. O catálogo de órgãos estaduais já existe;
   falta um coletor por estado (começar por SP, MG, RJ, RS, PR, BA, GO e DF).
2. **Classificação por regras.** Regex é auditável e barato, mas erra. Para os
   atos ambíguos, o próximo passo é usar a API do Claude como segunda opinião,
   com saída estruturada.
3. **Alertas.** Notificar por Telegram ou e-mail quando um concurso mudar de
   fase, usando o `feed.xml` ou um hook pós-coleta.
4. **Um órgão, vários concursos.** Hoje o agrupamento é um ciclo por órgão. Se
   o mesmo órgão tiver dois concursos simultâneos (por exemplo, PF para agente
   e para delegado), eles se fundem; o próximo passo é separar por cargo.
