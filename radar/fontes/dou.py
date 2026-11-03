"""Diário Oficial da União (Imprensa Nacional).

Usa a página pública "Leitura do Jornal" (https://www.in.gov.br/leiturajornal),
que embute a lista de atos do dia num bloco JSON
(<script id="params" type="application/json">). Para os atos que passam no
pré-filtro, baixa a íntegra em https://www.in.gov.br/web/dou/-/<urlTitle>.

Seções:
  do1 – atos normativos (portarias de autorização do MGI, comissões...)
  do2 – atos de pessoal (nomeações, homologações em alguns órgãos)
  do3 – contratos, licitações, extratos e editais
"""

from __future__ import annotations

import html
import json
import re
from datetime import date

from ..modelos import Publicacao
from . import http_get

BASE = "https://www.in.gov.br"
SECOES = ("do1", "do2", "do3")

_PARAMS_RE = re.compile(
    r'<script[^>]*id=["\']params["\'][^>]*>(.*?)</script>', re.S | re.I
)
_PRE_FILTRO = re.compile(r"concurso", re.I)


def parse_leitura(pagina: str) -> list[dict]:
    m = _PARAMS_RE.search(pagina)
    if not m:
        return []
    dados = json.loads(html.unescape(m.group(1)))
    return dados.get("jsonArray", []) or []


def _limpar_html(trecho: str) -> str:
    trecho = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", trecho, flags=re.S | re.I)
    trecho = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", trecho, flags=re.I)
    trecho = re.sub(r"<[^>]+>", " ", trecho)
    return re.sub(r"[ \t]+", " ", html.unescape(trecho)).strip()


def parse_integra(pagina: str) -> str:
    m = re.search(r'<div[^>]*class="[^"]*texto-dou[^"]*"[^>]*>(.*?)</div>\s*(?:<div|</article|$)',
                  pagina, re.S | re.I)
    return _limpar_html(m.group(1) if m else pagina)


def _data_iso(data_br: str, padrao: date) -> str:
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", data_br or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else padrao.isoformat()


def para_publicacao(item: dict, dia: date, texto: str | None = None) -> Publicacao:
    url_title = item.get("urlTitle", "")
    return Publicacao(
        fonte="DOU",
        data=_data_iso(item.get("pubDate", ""), dia),
        titulo=item.get("title") or item.get("titulo") or "",
        texto=texto if texto is not None else _limpar_html(item.get("content", "")),
        url=f"{BASE}/web/dou/-/{url_title}" if url_title else f"{BASE}/leiturajornal?data={dia:%d-%m-%Y}",
        hierarquia=item.get("hierarchyStr", ""),
    )


def coletar(dia: date, secoes=SECOES, integra: bool = True) -> list[Publicacao]:
    pubs: list[Publicacao] = []
    for secao in secoes:
        pagina = http_get(f"{BASE}/leiturajornal", {"data": f"{dia:%d-%m-%Y}", "secao": secao})
        for item in parse_leitura(pagina):
            resumo = f"{item.get('title', '')} {item.get('content', '')} {item.get('artType', '')}"
            if not _PRE_FILTRO.search(resumo):
                continue
            texto = None
            if integra and item.get("urlTitle"):
                try:
                    texto = parse_integra(http_get(f"{BASE}/web/dou/-/{item['urlTitle']}"))
                except Exception:  # noqa: BLE001 - se a íntegra falhar, fica o resumo
                    texto = None
            pubs.append(para_publicacao(item, dia, texto))
    return pubs
