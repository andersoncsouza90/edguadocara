"""Gera o site estático do radar (GitHub Pages: pasta docs/)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from .registro import Registro

MODELO = Path(__file__).with_name("modelo_site.html")


def gerar(registro: Registro, saida: Path = Path("docs"), hoje: date | None = None) -> Path:
    hoje = hoje or date.today()
    saida.mkdir(parents=True, exist_ok=True)
    concursos = sorted(
        (c.para_site(hoje) for c in registro.concursos.values()),
        key=lambda c: c["atualizado_em"], reverse=True,
    )
    payload = {"gerado_em": hoje.isoformat(), "concursos": concursos}
    bruto = json.dumps(payload, ensure_ascii=False)

    (saida / "concursos.json").write_text(bruto, encoding="utf-8")
    pagina = MODELO.read_text(encoding="utf-8").replace("__DADOS__", bruto.replace("</", "<\\/"))
    (saida / "index.html").write_text(pagina, encoding="utf-8")
    (saida / "feed.xml").write_text(_rss(concursos), encoding="utf-8")
    (saida / ".nojekyll").write_text("", encoding="utf-8")
    estatico = Path(__file__).with_name("static")
    if estatico.is_dir():
        (saida / "assets").mkdir(exist_ok=True)
        for arq in estatico.iterdir():
            (saida / "assets" / arq.name).write_bytes(arq.read_bytes())
    return saida / "index.html"


def _rss(concursos: list[dict], limite: int = 60) -> str:
    fatos = [(f, c) for c in concursos for f in c["linha_do_tempo"] if f["campo"] != "nota"]
    fatos.sort(key=lambda par: par[0]["data"], reverse=True)
    itens = []
    for f, c in fatos[:limite]:
        dt = datetime.fromisoformat(f["data"]).replace(tzinfo=timezone.utc)
        titulo = f"[{c['id']}] {f['campo'].replace('_', ' ')}: {f['valor']} ({f['veiculo']})"
        itens.append(
            "<item>"
            f"<title>{escape(titulo)}</title>"
            f"<link>{escape(f['url'])}</link>"
            f"<guid isPermaLink=\"false\">{escape(c['id'] + '|' + f['campo'] + '|' + str(f['valor']) + '|' + f['url'])}</guid>"
            f"<pubDate>{format_datetime(dt)}</pubDate>"
            f"<description>{escape(c['orgao'] + ' — ' + (f.get('nota') or ''))}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        "<title>Radar de Concursos – Fiscal, Controle e Policial</title>"
        "<link>https://github.com/andersoncsouza90/edguadocara</link>"
        "<description>Andamento de concursos com fonte de cada informação</description>"
        + "".join(itens) + "</channel></rss>\n"
    )
