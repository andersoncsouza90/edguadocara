---
name: radar-curadoria
description: Rotina de curadoria do Radar de Concursos (fiscal, controle, policial). Use quando pedirem para atualizar o radar, rodar a curadoria, monitorar concursos, registrar notícia/andamento de concurso (autorização, comissão, banca, edital) ou importar dados do PCI Concursos.
---

# Curadoria do Radar de Concursos

Você atualiza `data/concursos/*.json` (um arquivo por concurso, ID único
`SIGLA[-CARREIRA]-ANO`) usando **só a CLI** `python -m radar`. Nunca edite os
JSON à mão: a CLI valida fonte, datas e valores.

## 0. Contexto

```bash
python -m radar listar
```

Anote os concursos que **ainda não têm edital** (previstos, solicitados,
autorizados, comissão formada, banca em contratação/definida/contratada). São
eles que pedem acompanhamento de notícias.

## 1. PCI Concursos (editais publicados)

O PCI só lista concursos com edital aberto ou prestes a abrir. Chame as
ferramentas do MCP e **salve cada retorno, exatamente como veio**, num arquivo
JSON no scratchpad. Retornos grandes já vêm salvos em arquivo; os pequenos
você grava com Write. Depois importe:

```bash
python -m radar importar-pci <arquivos.json>
```

Buscas mínimas:
- `pesquisar_concursos`: "policia civil", "policia militar", "policia penal",
  "policia federal", "rodoviaria federal", "receita", "fazenda", "sefaz",
  "tribunal de contas", "controladoria"
- `buscar_por_cargo`: "auditor fiscal", "fiscal de tributos", "analista
  tributario", "auditor de controle", "controle interno", "controle externo",
  "delegado", "agente de policia", "escrivao", "investigador", "soldado",
  "policial penal"

O importador já descarta o que não é da área (universidades, TRTs,
conselhos) e não copia vagas e salário do edital inteiro quando só parte dos
cargos é da área. Não contorne essas regras.

## 2. Notícias (fases antes do edital)

Para cada concurso sem edital, rode a WebSearch no modo `standard` com
"concurso <órgão> <ano> banca edital". Use `extended` só se o resultado vier
fraco. Depois faça buscas de descoberta:
- "concurso auditor fiscal autorizado"
- "concurso SEFAZ banca definida"
- "concurso polícia civil autorização"
- "concurso polícia militar comissão formada"
- "concurso tribunal de contas banca"
- "concurso Receita Federal", "concurso PF", "concurso PRF", "concurso TCU",
  "concurso CGU", "concurso Polícia Penal Federal"

Fontes preferidas: Folha Dirigida/Qconcursos, JC Concursos, Estratégia, Gran,
Direção, Concursos no Brasil, PCI (notícias) e o site do órgão/DOU (oficial).

### Registrar um fato

```bash
python -m radar fato <ID> --campo <campo> --valor <valor> \
  --fonte-tipo imprensa --veiculo "<veículo>" --url "<url>" --data AAAA-MM-DD \
  --nota "<o que a fonte diz, em uma frase>"
```

- `--fonte-tipo oficial` só para DOU/DOE, site ou ofício do próprio órgão, ou
  processo SEI. Notícia que *cita* uma portaria continua sendo `imprensa`;
  ponha o número da portaria na `--nota`.
- `--data` é a data do fato noticiado (ex.: publicação da portaria). Se não
  souber, use a data de hoje e escreva "data da verificação" na nota. Nunca
  invente uma data.
- **Registre o mesmo fato em 2 veículos diferentes** sempre que possível: é
  isso que o confirma no site. Fato de um só veículo aparece como "sinal".

### Qual status registrar

| Status | Só registre quando a fonte disser que... |
|---|---|
| `previsto` | consta em PLOA/LOA, plano anual ou anúncio oficial de que haverá concurso |
| `solicitado` | o pedido de autorização foi enviado (ex.: ao MGI ou ao governador) |
| `autorizado` | saiu o ato de autorização (portaria, decreto, lei) |
| `comissao_formada` | foi publicada a portaria da comissão organizadora |
| `banca_em_definicao` | o processo de contratação da banca está em andamento (minuta, cotação, termo de referência) |
| `banca_definida` | o órgão **confirmou** a banca escolhida (dispensa ratificada ou anúncio oficial) |
| `banca_contratada` | o contrato foi assinado ou o extrato foi publicado |
| `edital_publicado` | o edital de abertura saiu |
| `homologado` | o resultado final foi homologado |

### Banca: os erros mais comuns

- Banca **especulada, favorita ou "em negociação"** vai em `--campo
  banca_cotada`, nunca em `--campo banca`.
- Nunca deduza a banca do concurso anterior. Ela vai em `--banca-anterior`
  quando você cria o concurso.
- `--campo banca` só junto com o status `banca_definida`, `banca_contratada`
  ou `edital_publicado`.

### Não misture concursos

- Antes de criar um concurso, confira em `radar listar` e nos `aliases` se
  ele já existe.
- O ID usa o ano do **primeiro ato do ciclo** (pedido ou autorização) e não
  muda depois. Um edital que sai em 2027 continua em `RFB-2026`; adicione
  `RECEITA-FEDERAL-2027` em `--aliases` se a imprensa usar esse nome.
- Se o mesmo órgão tiver concursos separados (policial e administrativo, por
  exemplo), use `--carreira`: `PRF-2026` e `PRF-ADM-2026`.
- Notícias sobre o concurso **anterior** (nomeações, *sub judice*,
  convocações, validade) não mudam a fase do concurso novo. Na dúvida,
  registre como `--campo nota`.
- Vagas e salário só valem se forem **deste** concurso e destes cargos.

### Criar concurso novo

```bash
python -m radar novo --sigla SEFAZ-SP --ano 2026 --orgao "Secretaria da Fazenda e Planejamento de SP" \
  --area fiscal --esfera estadual --uf SP --cargos "Auditor Fiscal Tributário Estadual" \
  --banca-anterior FCC --banca-anterior-ano 2013
```

Siglas padrão: RFB, PF, PRF, PPF, TCU, CGU, STN, MTE-AFT, SEFAZ-UF, TCE-UF,
TCM-UF, CGE-UF, PC-UF, PM-UF, PP-UF, PREF-CIDADE-UF.

## 3. Conferência no Diário Oficial (opcional, fase 2)

Se tiver acesso a www.in.gov.br, rode `python -m radar conferir --dias 3`. O
comando só **sugere** comandos `radar fato` com fonte oficial; revise cada um
antes de executar.

## 4. Fechamento

```bash
python -m radar validar
```

```bash
python -m unittest discover -s tests
```

```bash
python -m radar site
```

Faça o commit de `data/` e `docs/` com a mensagem
`curadoria: AAAA-MM-DD – <n> concursos atualizados` e dê push no branch
configurado.

No relatório final, liste as **mudanças de fase** do dia (ex.: "RFB-2026:
Autorizado → Banca em contratação"), os sinais ainda não confirmados e as
fontes que divergem entre si.
