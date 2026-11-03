"""Acompanhamento manual (curadoria).

Fases como "previsto" e "solicitado" quase nunca saem em diário oficial:
aparecem em PLOA/LOA (Anexo V), ofícios, entrevistas e notícias. Cadastre-as
em data/acompanhamento_manual.json – sempre com o link da fonte.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..modelos import Area, Evento, Orgao, TipoEvento

ARQUIVO = Path("data/acompanhamento_manual.json")


def carregar(caminho: Path = ARQUIVO) -> list[Evento]:
    if not caminho.exists():
        return []
    itens = json.loads(caminho.read_text(encoding="utf-8"))
    eventos = []
    for it in itens:
        area = Area(it["area"])
        orgao = Orgao(
            nome=it["orgao"],
            sigla=it.get("sigla") or it["orgao"],
            area=area,
            esfera=it.get("esfera", "federal"),
            uf=it.get("uf"),
        )
        eventos.append(Evento(
            tipo=TipoEvento(it["tipo"]),
            data=it["data"],
            titulo=it["titulo"],
            url=it["url"],
            fonte=it.get("fonte", "Curadoria"),
            orgao=orgao,
            area=area,
            resumo=it.get("observacao", ""),
            banca=it.get("banca"),
            vagas=it.get("vagas"),
            salario_max=it.get("salario_max"),
            inscricoes_inicio=it.get("inscricoes_inicio"),
            inscricoes_fim=it.get("inscricoes_fim"),
            cargos=it.get("cargos", []),
        ))
    return eventos

