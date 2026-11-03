"""Querido Diário (Open Knowledge Brasil) – diários oficiais municipais.

API pública: https://queridodiario.ok.org.br/api/docs
Cobre centenas de municípios; é a forma mais barata de pegar concursos de
fiscal de tributos / auditor fiscal municipal, guardas e controladorias.
"""

from __future__ import annotations

from datetime import date

from ..modelos import Publicacao
from . import http_json

API = "https://api.queridodiario.ok.org.br/gazettes"

CONSULTAS = [
    '"concurso público" "auditor fiscal"',
    '"concurso público" "fiscal de tributos"',
    '"concurso público" "auditor de tributos"',
    '"concurso público" "fiscal de rendas"',
    '"concurso público" "controle interno"',
    '"concurso público" "controladoria"',
]


def coletar(desde: date, ate: date, consultas=CONSULTAS, por_pagina: int = 100) -> list[Publicacao]:
    pubs: dict[tuple[str, str], Publicacao] = {}
    for consulta in consultas:
        offset = 0
        while True:
            dados = http_json(API, {
                "querystring": consulta,
                "published_since": desde.isoformat(),
                "published_until": ate.isoformat(),
                "excerpt_size": 800,
                "number_of_excerpts": 3,
                "size": por_pagina,
                "offset": offset,
                "sort_by": "descending_date",
            })
            diarios = dados.get("gazettes", [])
            for g in diarios:
                for trecho in g.get("excerpts", []) or []:
                    chave = (g.get("url", ""), trecho[:120])
                    if chave in pubs:
                        continue
                    pubs[chave] = Publicacao(
                        fonte="Querido Diário",
                        data=g.get("date", desde.isoformat()),
                        titulo=f"Diário Oficial de {g.get('territory_name', '')}/{g.get('state_code', '')}"
                               f"{' – edição extra' if g.get('is_extra_edition') else ''}",
                        texto=trecho,
                        url=g.get("url") or g.get("txt_url") or "",
                        uf=g.get("state_code"),
                        municipio=g.get("territory_name"),
                    )
            offset += por_pagina
            if offset >= dados.get("total_gazettes", 0) or not diarios:
                break
    return list(pubs.values())
