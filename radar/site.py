"""Gera o site estático do radar (GitHub Pages: pasta docs/)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from .base import Base

MODELO = Path(__file__).with_name("modelo_site.html")


def gerar(base: Base, saida: Path = Path("docs"), hoje: date | None = None) -> Path:
    hoje = hoje or date.today()
    saida.mkdir(parents=True, exist_ok=True)
    concursos = sorted(
        (c.para_site(hoje) for c in base.concursos.values()),
        key=lambda c: c["atualizado_em"], reverse=True,
    )
    payload = {"gerado_em": hoje.isoformat(), "concursos": concursos}
    bruto = json.dumps(payload, ensure_ascii=False)

    (saida / "concursos.json").write_text(bruto, encoding="utf-8")
    pagina = MODELO.read_text(encoding="utf-8").replace("__DADOS__", bruto.replace("</", "<\\/"))
    (saida / "index.html").write_text(pagina, encoding="utf-8")
    (saida / "feed.xml").write_text(_rss(concursos), encoding="utf-8")
    (saida / ".nojekyll").write_text("", encoding="utf-8")
    return saida / "index.html"


def _rss(concursos: list[dict], limite: int = 60) -> str:
    eventos = [
        (ev, c) for c in concursos for ev in c["eventos"]
    ]
    eventos.sort(key=lambda par: par[0]["data"], reverse=True)
    itens = []
    for ev, c in eventos[:limite]:
        dt = datetime.fromisoformat(ev["data"]).replace(tzinfo=timezone.utc)
        titulo = f"[{c['area'].upper()}] {c['sigla']}: {ev['tipo_rotulo']}"
        itens.append(
            "<item>"
            f"<title>{escape(titulo)}</title>"
            f"<link>{escape(ev['url'])}</link>"
            f"<guid isPermaLink=\"false\">{escape(c['chave'] + '|' + ev['url'] + '|' + ev['tipo'])}</guid>"
            f"<pubDate>{format_datetime(dt)}</pubDate>"
            f"<description>{escape(ev['titulo'])}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        "<title>Radar de Concursos – Fiscal, Controle e Policial</title>"
        "<link>https://github.com/andersoncsouza90/edguadocara</link>"
        "<description>Atos oficiais de concursos monitorados no DOU e diários oficiais</description>"
        + "".join(itens) + "</channel></rss>\n"
    )
