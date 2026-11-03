# Radar de Concursos — Fiscal · Controle · Policial

Acompanha cada concurso **do pedido à homologação**, com **ID único** e a
**fonte de cada informação**. Exemplos: `RFB-2026` (Banca em contratação),
`PRF-2026` (Solicitado), `PC-PE-2026` (Inscrições abertas).

## Como funciona

```
 notícias especializadas ─┐                       ┌─> docs/index.html (site)
 PCI Concursos (MCP) ─────┼─> agente de curadoria ─┤   docs/concursos.json
 DOU (conferência) ───────┘   (python -m radar)   └─> docs/feed.xml (RSS)
                                   │
                         data/concursos/<ID>.json
                     (um arquivo por concurso, só fatos com fonte)
```

1. **Curadoria.** Um agente Claude segue a skill
   `.claude/skills/radar-curadoria`. Ele consulta o MCP da PCI Concursos e
   faz buscas na web, e grava fatos pela CLI (`radar fato`, `radar
   importar-pci`). A CLI recusa qualquer fato sem URL, data ou valor válido.
2. **Consolidação.** Status, banca, vagas e inscrições são recalculados a
   partir dos fatos, segundo as regras de confiança abaixo.
3. **Publicação.** O GitHub Actions roda os testes, valida o registro e gera
   o site a cada mudança e uma vez por dia.
4. **Conferência no DOU (fase 2).** `radar conferir` lê o Diário Oficial e
   **sugere** fatos oficiais para os concursos já registrados. Ele não grava
   nada sozinho.

## Regras de confiança

| Fonte | Peso | Confirma sozinha? |
|---|---|---|
| Oficial (DOU/DOE, site do órgão, SEI) | 3 | Sim |
| PCI Concursos | 2 | Sim, para dados de edital (o PCI só lista edital publicado) |
| Imprensa especializada | 1 | Não. Precisa de **2 veículos diferentes** com o mesmo valor |

- Fato de um único veículo aparece no site como **"sinal"**: ele não muda a
  fase.
- Banca **cotada** (especulação) fica separada da banca **definida ou
  contratada**. A **banca do concurso anterior** também aparece à parte.
  Juntar essas três coisas era o principal erro da primeira versão.
- Quando as fontes de mesmo peso divergem (ex.: 146 contra 150 vagas), o site
  mostra os dois valores.
- O status nunca regride, e toda informação tem link para a fonte.

## Fases

| Fase | O que a comprova |
|---|---|
| Previsto | PLOA/LOA, plano anual, anúncio oficial |
| Solicitado | Pedido de autorização enviado (ex.: ao MGI) |
| Autorizado | Portaria/ato de autorização. No âmbito federal, o Decreto 9.739/2019 dá 6 meses para publicar o edital |
| Comissão formada | Portaria da comissão organizadora |
| Banca em contratação | Processo de contratação em curso (minuta, termo de referência) |
| Banca definida | Escolha confirmada pelo órgão (em geral, dispensa com base na Lei 14.133/2021, art. 75, XV) |
| Banca contratada | Contrato assinado ou extrato publicado |
| Edital publicado | Edital de abertura |
| Homologado | Resultado final homologado, início da validade (CF/88, art. 37, III) |

## IDs

`SIGLA[-CARREIRA]-ANO`: `RFB-2026`, `PRF-ADM-2026`, `SEFAZ-SP-2026`,
`PREF-CURITIBA-PR-2026`. O ano é o do **primeiro ato do ciclo** e não muda;
outros nomes vão em `aliases`.

## Uso

```bash
python -m radar listar
```

```bash
python -m radar ver RFB-2026
```

```bash
python -m radar fato RFB-2026 --campo status --valor banca_contratada --fonte-tipo oficial --veiculo DOU --url "https://www.in.gov.br/..." --data 2026-11-20
```

```bash
python -m radar importar-pci resultado_pci.json
```

```bash
python -m radar validar
```

```bash
python -m radar site
```

```bash
python -m unittest discover -s tests
```

Valores aceitos em `--campo`: `status`, `banca`, `banca_cotada`, `vagas`,
`salario_max`, `inscricoes_inicio`, `inscricoes_fim`, `edital_url`,
`previsao` e `nota`.

## Direitos autorais

O registro guarda **fatos** (fase, banca, vagas, datas) com link para a
fonte, e não reproduz o texto das notícias. Atos oficiais não têm proteção
autoral (Lei 9.610/1998, art. 8º, IV). Já uma base de dados organizada é
protegida (art. 7º, XIII), e por isso não copiamos a base de agregadores: o
PCI entra pelo MCP oficial e cada item aponta para a página dele.

## Publicação do site

*Settings → Pages → Deploy from a branch*, pasta `/docs`.
