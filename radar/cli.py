"""Linha de comando: python -m radar <comando>."""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from . import site
from .base import Base
from .classificador import classificar
from .fontes import dou, manual, querido_diario
from .modelos import Area, Publicacao


def _datas(desde: date, ate: date):
    # inclui fins de semana: o DOU publica edições extras
    d = desde
    while d <= ate:
        yield d
        d += timedelta(days=1)


def cmd_coletar(a) -> int:
    base = Base(Path(a.base))
    ate = date.fromisoformat(a.ate) if a.ate else date.today()
    desde = date.fromisoformat(a.desde) if a.desde else ate - timedelta(days=a.dias - 1)
    areas = {Area(x) for x in a.areas.split(",")}
    fontes = set(a.fontes.split(","))
    novos = falhas = 0

    pubs: list[Publicacao] = []
    if "dou" in fontes:
        for dia in _datas(desde, ate):
            try:
                pubs += dou.coletar(dia, integra=not a.sem_integra)
            except Exception as e:  # noqa: BLE001
                falhas += 1
                print(f"[DOU {dia}] falhou: {e}", file=sys.stderr)
    if "qd" in fontes:
        try:
            pubs += querido_diario.coletar(desde, ate)
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"[Querido Diário] falhou: {e}", file=sys.stderr)

    for pub in pubs:
        ev = classificar(pub, areas)
        if ev and base.adicionar(ev):
            novos += 1
            print(f"+ {ev.data} {ev.area.value:<8} {ev.orgao.sigla:<14} {ev.tipo.rotulo}: {ev.titulo[:80]}")
    for ev in manual.carregar(Path(a.manual)):
        if base.adicionar(ev):
            novos += 1
    base.salvar()
    print(f"{len(pubs)} publicações lidas, {novos} eventos novos, {falhas} falhas de fonte "
          f"({desde} a {ate}).")
    return 1 if falhas and not pubs else 0


def cmd_listar(a) -> int:
    base = Base(Path(a.base))
    hoje = date.today()
    for c in sorted(base.concursos.values(), key=lambda c: c.ultima_data, reverse=True):
        grupo, fase = c.grupo(hoje)
        if (a.area and c.area.value != a.area) or (a.grupo and grupo != a.grupo):
            continue
        print(f"{c.ultima_data}  {c.area.value:<8} {c.orgao.sigla:<14} {fase:<22} "
              f"banca={c.banca or '-':<12} vagas={c.vagas or '-'}")
    return 0


def cmd_site(a) -> int:
    base = Base(Path(a.base))
    for ev in manual.carregar(Path(a.manual)):
        base.adicionar(ev)
    print(f"Site gerado em {site.gerar(base, Path(a.saida))}")
    return 0


def cmd_classificar(a) -> int:
    """Testa o classificador com um texto colado (útil para calibrar regras)."""
    texto = sys.stdin.read() if a.arquivo == "-" else Path(a.arquivo).read_text(encoding="utf-8")
    titulo, _, corpo = texto.partition("\n")
    ev = classificar(Publicacao("manual", date.today().isoformat(), titulo, corpo, "-"))
    if not ev:
        print("Não classificado como concurso das áreas monitoradas.")
        return 1
    for campo in ("tipo", "area", "banca", "vagas", "salario_max", "inscricoes_inicio",
                  "inscricoes_fim", "cargos"):
        v = getattr(ev, campo)
        print(f"{campo:>18}: {getattr(v, 'value', v)}")
    print(f"{'orgao':>18}: {ev.orgao.nome} ({ev.orgao.sigla}, {ev.orgao.esfera}, {ev.orgao.uf or '-'})")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="radar", description="Radar de concursos (fiscal, controle, policial)")
    p.add_argument("--base", default=str(Path("data/radar.json")))
    p.add_argument("--manual", default=str(manual.ARQUIVO))
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("coletar", help="baixa e classifica atos das fontes")
    c.add_argument("--desde"), c.add_argument("--ate")
    c.add_argument("--dias", type=int, default=1, help="quantos dias para trás (padrão: só hoje)")
    c.add_argument("--fontes", default="dou,qd")
    c.add_argument("--areas", default="fiscal,controle,policial")
    c.add_argument("--sem-integra", action="store_true", help="não baixa a íntegra dos atos do DOU")
    c.set_defaults(f=cmd_coletar)

    l = sub.add_parser("listar", help="lista concursos da base")
    l.add_argument("--area"), l.add_argument("--grupo")
    l.set_defaults(f=cmd_listar)

    s = sub.add_parser("site", help="gera o site estático")
    s.add_argument("--saida", default="docs")
    s.set_defaults(f=cmd_site)

    k = sub.add_parser("classificar", help="classifica um texto (1ª linha = título)")
    k.add_argument("arquivo", nargs="?", default="-")
    k.set_defaults(f=cmd_classificar)

    a = p.parse_args(argv)
    return a.f(a)
