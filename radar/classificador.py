"""Classificação de atos oficiais: é concurso? de qual área, órgão, fase e banca?

Todas as regras trabalham sobre texto *normalizado* (minúsculo, sem acentos,
espaços colapsados), o que torna as expressões regulares mais simples e
robustas a variações de grafia dos diários oficiais.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from .modelos import Area, Evento, Orgao, Publicacao, TipoEvento

# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------


def normalizar(texto: str | None) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[‐-―]", "-", t)
    return re.sub(r"\s+", " ", t).strip()


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-")


ESTADOS = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
    "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
    "maranhao": "MA", "mato grosso do sul": "MS", "mato grosso": "MT",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}
UFS = set(ESTADOS.values())
_ESTADO_RE = "(" + "|".join(sorted(ESTADOS, key=len, reverse=True)) + r")\b"
_PREP = r"(?:de |do |da )?"

# ---------------------------------------------------------------------------
# Catálogo de órgãos (ordem importa: os mais específicos primeiro)
# ---------------------------------------------------------------------------

_ORGAOS_FIXOS: list[tuple[str, Orgao]] = [
    (r"\brfb\b", Orgao("Receita Federal do Brasil", "RFB", Area.FISCAL)),
    (r"\bprf\b", Orgao("Polícia Rodoviária Federal", "PRF", Area.POLICIAL)),
    (r"\btcu\b", Orgao("Tribunal de Contas da União", "TCU", Area.CONTROLE)),
    (r"\bcgu\b", Orgao("Controladoria-Geral da União", "CGU", Area.CONTROLE)),
    (r"\bdpf\b|[-\u2013]\s*pf\b", Orgao("Polícia Federal", "PF", Area.POLICIAL)),
    (r"policia rodoviaria federal", Orgao("Polícia Rodoviária Federal", "PRF", Area.POLICIAL)),
    (r"policia penal federal|secretaria nacional de politicas penais",
     Orgao("Polícia Penal Federal", "PPF", Area.POLICIAL)),
    (r"policia federal", Orgao("Polícia Federal", "PF", Area.POLICIAL)),
    (r"receita federal", Orgao("Receita Federal do Brasil", "RFB", Area.FISCAL)),
    (r"auditor[- ]fiscal do trabalho|inspecao do trabalho",
     Orgao("Ministério do Trabalho e Emprego (Auditor-Fiscal do Trabalho)", "MTE-AFT", Area.FISCAL)),
    (r"procuradoria[- ]geral da fazenda nacional",
     Orgao("Procuradoria-Geral da Fazenda Nacional", "PGFN", Area.FISCAL)),
    (r"tribunal de contas da uniao", Orgao("Tribunal de Contas da União", "TCU", Area.CONTROLE)),
    (r"controladoria[- ]geral da uniao", Orgao("Controladoria-Geral da União", "CGU", Area.CONTROLE)),
    (r"secretaria do tesouro nacional",
     Orgao("Secretaria do Tesouro Nacional", "STN", Area.CONTROLE)),
    (r"tribunal de contas do distrito federal",
     Orgao("Tribunal de Contas do Distrito Federal", "TCDF", Area.CONTROLE, "estadual", "DF")),
    (r"controladoria[- ]geral do distrito federal",
     Orgao("Controladoria-Geral do Distrito Federal", "CGDF", Area.CONTROLE, "estadual", "DF")),
    (r"tribunal de contas do municipio d[eo] sao paulo",
     Orgao("Tribunal de Contas do Município de São Paulo", "TCM-SP", Area.CONTROLE, "municipal", "SP")),
    (r"tribunal de contas do municipio d[eo] rio de janeiro",
     Orgao("Tribunal de Contas do Município do Rio de Janeiro", "TCM-RJ", Area.CONTROLE, "municipal", "RJ")),
]

# (regex com grupo do estado, nome-modelo, sigla-modelo, área)
_ORGAOS_ESTADUAIS: list[tuple[str, str, str, Area]] = [
    (r"policia civil (?:do estado )?" + _PREP + _ESTADO_RE, "Polícia Civil", "PC-{uf}", Area.POLICIAL),
    (r"policia militar (?:do estado )?" + _PREP + _ESTADO_RE, "Polícia Militar", "PM-{uf}", Area.POLICIAL),
    (r"policia penal (?:do estado )?" + _PREP + _ESTADO_RE, "Polícia Penal", "PP-{uf}", Area.POLICIAL),
    (r"policia cientifica (?:do estado )?" + _PREP + _ESTADO_RE, "Polícia Científica", "PCI-{uf}", Area.POLICIAL),
    (r"tribunal de contas dos municipios (?:do estado )?" + _PREP + _ESTADO_RE,
     "Tribunal de Contas dos Municípios", "TCM-{uf}", Area.CONTROLE),
    (r"tribunal de contas (?:do estado )?" + _PREP + _ESTADO_RE,
     "Tribunal de Contas do Estado", "TCE-{uf}", Area.CONTROLE),
    (r"controladoria[- ]geral do estado " + _PREP + _ESTADO_RE,
     "Controladoria-Geral do Estado", "CGE-{uf}", Area.CONTROLE),
    (r"secretaria (?:de estado )?(?:da |de )?(?:fazenda|economia|financas|tributacao|receita)"
     r"(?: e [a-z ]{3,30}?)?(?: do estado)? " + _PREP + _ESTADO_RE,
     "Secretaria da Fazenda", "SEFAZ-{uf}", Area.FISCAL),
    (r"receita estadual " + _PREP + _ESTADO_RE, "Receita Estadual", "SEFAZ-{uf}", Area.FISCAL),
]

_SIGLAS_ESTADUAIS = {
    "sefaz": ("Secretaria da Fazenda", "SEFAZ-{uf}", Area.FISCAL),
    "tce": ("Tribunal de Contas do Estado", "TCE-{uf}", Area.CONTROLE),
    "cge": ("Controladoria-Geral do Estado", "CGE-{uf}", Area.CONTROLE),
    "pc": ("Polícia Civil", "PC-{uf}", Area.POLICIAL),
    "pm": ("Polícia Militar", "PM-{uf}", Area.POLICIAL),
    "pp": ("Polícia Penal", "PP-{uf}", Area.POLICIAL),
}
_SIGLA_RE = re.compile(r"\b(sefaz|tce|cge|pc|pm|pp)[-/]([a-z]{2})\b")


def identificar_orgao(texto_norm: str) -> Orgao | None:
    """Encontra o órgão do catálogo que aparece primeiro no texto."""
    candidatos: list[tuple[int, Orgao]] = []
    for padrao, org in _ORGAOS_FIXOS:
        m = re.search(padrao, texto_norm)
        if m:
            candidatos.append((m.start(), Orgao(**vars(org))))
    for padrao, nome, sigla, area in _ORGAOS_ESTADUAIS:
        m = re.search(padrao, texto_norm)
        if m:
            uf = ESTADOS[m.group(1)]
            candidatos.append(
                (m.start(), Orgao(f"{nome} — {uf}", sigla.format(uf=uf), area, "estadual", uf))
            )
    for m in _SIGLA_RE.finditer(texto_norm):
        uf = m.group(2).upper()
        if uf in UFS:
            nome, sigla, area = _SIGLAS_ESTADUAIS[m.group(1)]
            candidatos.append(
                (m.start(), Orgao(f"{nome} — {uf}", sigla.format(uf=uf), area, "estadual", uf))
            )
    if not candidatos:
        return None
    return min(candidatos, key=lambda c: c[0])[1]


# ---------------------------------------------------------------------------
# Área (quando o órgão não está no catálogo, ex.: prefeituras)
# ---------------------------------------------------------------------------

_SINAIS_AREA: dict[Area, list[str]] = {
    Area.FISCAL: [
        r"auditor[- ]fiscal", r"analista[- ]tributario", r"tecnico[- ]tributario",
        r"fiscal (?:de |da )?(?:tributos|rendas?|receitas?|tributario)", r"agente fiscal",
        r"auditor (?:de |da )?(?:tributos|receita|tributario)", r"fiscal de posturas",
        r"gestor fazendario", r"auditor fiscal",
    ],
    Area.CONTROLE: [
        r"tribunal de contas", r"controladoria", r"controle externo", r"controle interno",
        r"auditor (?:de )?controle", r"analista de controle", r"auditor governamental",
        r"auditor federal de financas e controle",
    ],
    Area.POLICIAL: [
        r"policia (?:federal|rodoviaria|civil|militar|penal|legislativa|cientifica)",
        r"delegado de policia", r"agente de policia", r"escrivao de policia",
        r"investigador de policia", r"papiloscopista", r"perito (?:criminal|oficial)",
        r"soldado (?:pm|da policia|policial)", r"policial (?:penal|civil|militar|rodoviario)",
        r"agente penitenciario",
    ],
}


def pontuar_areas(cabecalho: str, texto: str) -> dict[Area, int]:
    pontos = {a: 0 for a in Area}
    for area, padroes in _SINAIS_AREA.items():
        for p in padroes:
            if re.search(p, cabecalho):
                pontos[area] += 2
            elif re.search(p, texto):
                pontos[area] += 1
    return pontos


def detectar_area(cabecalho: str, texto: str, orgao: Orgao | None) -> Area | None:
    if orgao and orgao.area:
        return orgao.area
    pontos = pontuar_areas(cabecalho, texto)
    melhor = max(pontos, key=lambda a: pontos[a])
    return melhor if pontos[melhor] > 0 else None


# ---------------------------------------------------------------------------
# Tipo do ato (qual fase do concurso ele comprova)
# ---------------------------------------------------------------------------

# Regras avaliadas no CABEÇALHO (título + início do texto), na ordem.
# Atos "terminais" (homologação, cancelamento...) só valem no cabeçalho para
# evitar falsos positivos: todo edital de abertura menciona a homologação futura.
_REGRAS_CABECALHO: list[tuple[TipoEvento, list[str]]] = [
    (TipoEvento.HOMOLOGACAO, [r"homolog\w*\s.{0,160}resultado final", r"resultado final.{0,160}homolog",
                              r"homolog\w*\s.{0,40}concurso"]),
    (TipoEvento.CANCELAMENTO, [r"(?:cancela|anula|revoga)\w*\s.{0,30}(?:concurso|edital)"]),
    (TipoEvento.SUSPENSAO, [r"suspen(?:de|der|sao|so|sa)\w*\s.{0,60}(?:concurso|edital)"]),
    (TipoEvento.RETIFICACAO, [r"retifica\w*", r"errata"]),
]

# Regras avaliadas no texto inteiro, na ordem.
_REGRAS_TEXTO: list[tuple[TipoEvento, list[str]]] = [
    (TipoEvento.EDITAL_ABERTURA, [
        r"edital\s+(?:de\s+)?abertura", r"abertura\s+(?:das?\s+)?inscric",
        r"torna\w*\s+public\w*\s.{0,80}realizacao\s+de\s+concurso",
        r"estarao\s+abertas\s+as\s+inscric", r"inscricoes\s+estarao\s+abertas",
    ]),
    (TipoEvento.CONTRATO_BANCA, [r"extrato\s+d[eo]\s+contrato"]),
    (TipoEvento.BANCA_DEFINIDA, [
        r"dispensa\s+de\s+licitacao", r"inexigibilidade\s+de\s+licitacao",
        r"contratacao\s+direta", r"ratific\w*\s.{0,80}dispensa",
    ]),
    (TipoEvento.COMISSAO, [
        r"comissao\s+(?:organizadora|de\s+acompanhamento|especial|do\s+concurso|de\s+concurso|responsavel)",
        r"(?:constitui|institui|designa)\w*\s.{0,120}comissao\s.{0,160}concurso",
    ]),
    (TipoEvento.AUTORIZACAO, [
        r"autoriz\w*\s.{0,40}realizacao\s+de\s+concurso",
        r"fica\w*\s+autorizad\w*\s.{0,160}concurso\s+publico",
        r"autoriz\w*\s.{0,30}provimento\s+de\s.{0,120}cargos",
    ]),
    (TipoEvento.RESULTADO, [r"resultado\s+final"]),
    (TipoEvento.SOLICITACAO, [r"solicit\w*\s.{0,80}autorizacao\s.{0,80}concurso"]),
]

_CONCURSO_RE = re.compile(r"concurso\s+public")
# Atos de execução de concursos em andamento/antigos: não mudam a fase.
_JUDICIAL = re.compile(
    r"acao judicial|decisao judicial|acordao proferido|mandado de seguranca|forca executoria|cumprimento (?:a|de) (?:decisao|sentenca|acordao)"
)
_IGNORAR = re.compile(
    r"sub judice|reintegra\w*|nomea\w*|convoca\w*|exame medico|avaliacao medica|curso de formacao"
    r"|teste de aptidao|investigacao social|resultado (?:provisorio|preliminar)|prorroga\w* .{0,40}validade"
)


# Sinais inequívocos de edital de abertura: prevalecem sobre menções a
# homologação/cancelamento futuros ("a homologação será publicada...").
_ABERTURA_FORTE = re.compile(
    r"torna\w*\s+public\w*\s.{0,80}realizacao\s+de\s+concurso|estarao\s+abertas\s+as\s+inscric"
    r"|inscricoes\s+estarao\s+abertas"
)
_FUTURO = re.compile(r"\b(?:sera|serao|devera|deverao|podera|poderao)\b")


def _achou_terminal(padrao: str, cabecalho: str) -> bool:
    for m in re.finditer(padrao, cabecalho):
        contexto = cabecalho[max(0, m.start() - 60): m.end() + 60]
        if not _FUTURO.search(contexto):
            return True
    return False


def detectar_tipo(cabecalho: str, texto: str) -> TipoEvento | None:
    abertura_forte = bool(_ABERTURA_FORTE.search(cabecalho))
    for tipo, padroes in _REGRAS_CABECALHO:
        if abertura_forte and tipo is not TipoEvento.RETIFICACAO:
            break
        if any(_achou_terminal(p, cabecalho) for p in padroes):
            return tipo
    for tipo, padroes in _REGRAS_TEXTO:
        if any(re.search(p, texto) for p in padroes):
            return tipo
    return None


# ---------------------------------------------------------------------------
# Bancas organizadoras
# ---------------------------------------------------------------------------

BANCAS: list[tuple[str, str]] = [
    ("Cebraspe", r"cebraspe|centro brasileiro de pesquisa em avaliacao e selecao|\bcespe\b"),
    ("FGV", r"\bfgv\b|fundacao getulio vargas"),
    ("FCC", r"\bfcc\b|fundacao carlos chagas"),
    ("Vunesp", r"vunesp"),
    ("Cesgranrio", r"cesgranrio"),
    ("IBFC", r"\bibfc\b|instituto brasileiro de formacao e capacitacao"),
    ("Instituto AOCP", r"\baocp\b"),
    ("Idecan", r"idecan"),
    ("Quadrix", r"quadrix"),
    ("Instituto Consulplan", r"consulplan"),
    ("Fundatec", r"fundatec"),
    ("Ibade", r"\bibade\b"),
    ("Instituto Access", r"instituto access"),
    ("Avança SP", r"avanca sp"),
    ("Fundep", r"\bfundep\b"),
    ("Selecon", r"selecon"),
    ("Iades", r"\biades\b"),
    ("Fepese", r"fepese"),
    ("Objetiva Concursos", r"objetiva concursos|instituto objetiva"),
    ("IBGP", r"\bibgp\b"),
    ("Instituto Legatus", r"legatus"),
    ("Fundação La Salle", r"fundacao la salle"),
    ("Instituto Unifil", r"unifil\b"),
    ("Legalle", r"legalle"),
    ("Fumarc", r"fumarc"),
    ("Instituto Mais", r"instituto mais\b"),
    ("Ibam", r"\bibam\b"),
    ("Comperve", r"comperve"),
    ("NC-UFPR", r"nc[- ]ufpr|nucleo de concursos da universidade federal do parana"),
    ("Cetrede", r"cetrede"),
    ("Instituto Verbena", r"verbena"),
    ("ESAF", r"\besaf\b"),
]


def detectar_banca(texto: str) -> str | None:
    achados = [(m.start(), nome) for nome, p in BANCAS if (m := re.search(p, texto))]
    return min(achados)[1] if achados else None


# ---------------------------------------------------------------------------
# Extração de vagas, remuneração, inscrições e cargos
# ---------------------------------------------------------------------------

def _inteiro(s: str) -> int:
    return int(s.replace(".", ""))


def extrair_vagas(texto: str) -> int | None:
    num = r"(\d{1,3}(?:\.\d{3})+|\d+)"
    extenso = r"(?:\s*\([a-z\s-]+\))?"
    m = re.search(r"total\s+de\s+" + num + extenso + r"\s+(?:vagas|cargos)", texto)
    if m:
        return _inteiro(m.group(1))
    valores = [
        _inteiro(m.group(1))
        for m in re.finditer(num + extenso + r"\s+(?:vagas|cargos\s+(?:vagos|de))", texto)
    ]
    valores += [
        _inteiro(m.group(1))
        for m in re.finditer(r"provimento\s+de\s+" + num + extenso + r"\s+(?:vagas|cargos)", texto)
    ]
    valores = [v for v in valores if 0 < v < 100_000]
    return max(valores) if valores else None


def extrair_salario(texto: str) -> float | None:
    padrao = re.compile(
        r"(?:remunera\w*|subsidio|vencimento\w*|salario\w*)(?:(?!r\$).){0,160}?"
        r"r\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})"
    )
    valores = [float(m.group(1).replace(".", "").replace(",", ".")) for m in padrao.finditer(texto)]
    valores = [v for v in valores if 1_000 <= v <= 100_000]
    return max(valores) if valores else None


_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_MES = r"(\d{1,2}|" + "|".join(_MESES) + r")"
_SEP = r"\s*(?:/|\.|\s+de\s+)\s*"
_DATA = r"(\d{1,2})o?" + _SEP + _MES + _SEP + r"(\d{4})"


def _data(d: str, m: str, a: str) -> str | None:
    try:
        mes = int(m) if m.isdigit() else _MESES[m]
        return date(int(a), mes, int(d)).isoformat()
    except (ValueError, KeyError):
        return None


def extrair_inscricoes(texto: str) -> tuple[str | None, str | None]:
    for ancora in re.finditer(r"inscric", texto):
        janela = texto[ancora.start(): ancora.start() + 320]
        m = re.search(_DATA + r".{0,60}?\b(?:a|ate|e)\b.{0,40}?" + _DATA, janela)
        if m:
            g = m.groups()
            return _data(*g[0:3]), _data(*g[3:6])
        m = re.search(r"\b(\d{1,2})o?(?:" + _SEP + r"(\d{1,2}))?\s+(?:a|ate)\s+" + _DATA, janela)
        if m:
            d1, m1, d2, m2, a2 = m.groups()
            return _data(d1, m1 or m2, a2), _data(d2, m2, a2)
    return None, None


_CARGOS: list[tuple[str, str]] = [
    ("Auditor-Fiscal da Receita Federal", r"auditor[- ]fiscal da receita federal"),
    ("Analista-Tributário", r"analista[- ]tributario"),
    ("Auditor-Fiscal do Trabalho", r"auditor[- ]fiscal do trabalho"),
    ("Auditor Fiscal", r"auditor[- ]fiscal(?! da receita federal| do trabalho)"),
    ("Fiscal de Tributos", r"fiscal (?:de )?tributos"),
    ("Auditor de Controle Externo", r"auditor (?:de )?controle externo"),
    ("Auditor Federal de Finanças e Controle", r"auditor federal de financas e controle"),
    ("Técnico Federal de Finanças e Controle", r"tecnico federal de financas e controle"),
    ("Auditor de Controle Interno", r"auditor (?:de )?controle interno"),
    ("Delegado", r"delegado"),
    ("Agente de Polícia", r"agente de policia"),
    ("Escrivão", r"escrivao"),
    ("Investigador", r"investigador"),
    ("Papiloscopista", r"papiloscopista"),
    ("Perito Criminal", r"perito criminal"),
    ("Policial Rodoviário Federal", r"policial rodoviario federal"),
    ("Policial Penal", r"policial penal"),
    ("Soldado", r"soldado"),
    ("Oficial", r"oficial (?:combatente|da policia militar|pm)|cadete"),
]


def extrair_cargos(texto: str) -> list[str]:
    return [nome for nome, p in _CARGOS if re.search(p, texto)]


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def classificar(pub: Publicacao, areas: set[Area] | None = None) -> Evento | None:
    """Transforma uma publicação bruta num Evento do radar, ou None se não for relevante."""
    titulo = normalizar(pub.titulo)
    corpo = normalizar(pub.texto)
    texto = f"{titulo} {corpo}"
    if not _CONCURSO_RE.search(texto):
        return None

    cabecalho = f"{titulo} {corpo[:600]}"
    tipo = detectar_tipo(cabecalho, texto)
    if tipo is None:
        return None
    if tipo is TipoEvento.CONTRATO_BANCA and not (
        detectar_banca(texto) or re.search(r"(?:organizacao|realizacao|execucao)\s.{0,40}concurso", texto)
    ):
        return None

    if _IGNORAR.search(f"{titulo} {corpo[:300]}") and tipo is not TipoEvento.HOMOLOGACAO:
        return None
    # Atos de concursos anteriores não mudam a fase do concurso atual:
    # cumprimento de decisão judicial, ou ato "regido pelo Edital nº 1/2022".
    if _JUDICIAL.search(f"{titulo} {corpo[:900]}"):
        return None
    ano_ato = int(pub.data[:4]) if pub.data[:4].isdigit() else None
    regido = re.search(r"regid[oa]s? pelo edital n\S* \d+/(\d{4})", texto)
    if regido and ano_ato and int(regido.group(1)) < ano_ato:
        return None
    # Retificação só comprova edital publicado se for do edital de abertura
    # (nº 1 ou que trate de abertura/inscrições); senão é ato de execução.
    if tipo is TipoEvento.RETIFICACAO and not re.search(
            r"edital (?:de abertura|n\S* 0?1\b)|abertura|inscric", texto):
        return None

    # O órgão é o AUTOR do ato: título, hierarquia do diário e o início do
    # texto. Nunca o texto inteiro: editais de universidades citam "CPF
    # regular na Receita Federal" e isso não os torna concursos da RFB.
    orgao = (identificar_orgao(titulo) or identificar_orgao(normalizar(pub.hierarquia))
             or identificar_orgao(corpo[:400]))
    area = detectar_area(cabecalho, cabecalho, orgao)
    if area is None or (areas and area not in areas):
        return None
    if orgao is None:
        orgao = _orgao_fallback(pub, area)

    eh_edital = tipo in {TipoEvento.EDITAL_ABERTURA, TipoEvento.RETIFICACAO}
    inicio, fim = extrair_inscricoes(texto) if eh_edital else (None, None)
    return Evento(
        tipo=tipo,
        data=pub.data,
        titulo=pub.titulo.strip()[:300],
        url=pub.url,
        fonte=pub.fonte,
        orgao=orgao,
        area=area,
        resumo=re.sub(r"\s+", " ", pub.texto).strip()[:600],
        banca=detectar_banca(texto),
        vagas=extrair_vagas(texto),
        salario_max=extrair_salario(texto) if eh_edital else None,
        inscricoes_inicio=inicio,
        inscricoes_fim=fim,
        cargos=extrair_cargos(texto),
    )


def _orgao_fallback(pub: Publicacao, area: Area) -> Orgao:
    if pub.municipio:
        nome = f"Prefeitura de {pub.municipio}" + (f"/{pub.uf}" if pub.uf else "")
        return Orgao(nome, nome, area, "municipal", pub.uf)
    partes = [p.strip() for p in (pub.hierarquia or "").split("/") if p.strip()]
    nome = partes[1] if len(partes) > 1 else (partes[0] if partes else "Órgão não identificado")
    return Orgao(nome, nome, area, "federal" if pub.fonte == "DOU" else "estadual", pub.uf)
