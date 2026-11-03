"""Linha de comando: python -m radar <comando>.

Fluxo:
  1. Curadoria (agente Claude com MCP do PCI + busca na web, ou humano):
       radar novo / radar fato / radar importar-pci
  2. Publicação:   radar validar && radar site
  3. Conferência (fase 2, DOU): radar conferir  -> só SUGERE fatos oficiais
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from . import site
from .classificador import classificar
from .fontes import dou, pci
from .modelos import Area, Campo, Fato, FonteTipo, Publicacao, Status
from .registro import Concurso, ErroRegistro, Registro, gerar_id


def _registro(a) -> Registro:
    return Registro(Path(a.dados))


def cmd_novo(a) -> int:
    reg = _registro(a)
    cid = a.id or gerar_id(a.sigla, a.ano, a.carreira)
    c = reg.novo(Concurso(
        id=cid, orgao=a.orgao, sigla=a.sigla.upper(), area=Area(a.area), esfera=a.esfera, uf=a.uf,
        cargos=[x.strip() for x in (a.cargos or "").split(";") if x.strip()],
        aliases=[x.strip() for x in (a.aliases or "").split(";") if x.strip()],
        banca_anterior={"nome": a.banca_anterior, "ano": a.banca_anterior_ano, "url": a.banca_anterior_url}
        if a.banca_anterior else None,
    ))
    reg.salvar()
    print(f"criado {c.id}")
    return 0


def _valor(campo: Campo, bruto: str):
    if campo is Campo.VAGAS:
        return int(bruto.replace(".", ""))
    if campo is Campo.SALARIO_MAX:
        return float(bruto.replace(".", "").replace(",", ".")) if "," in bruto else float(bruto)
    if campo is Campo.STATUS:
        return Status(bruto).value
    return bruto


def cmd_fato(a) -> int:
    reg = _registro(a)
    c = reg.obter(a.id)
    campo = Campo(a.campo)
    f = Fato(campo, _valor(campo, a.valor), FonteTipo(a.fonte_tipo), a.veiculo, a.url, a.data, nota=a.nota or "")
    if c.adicionar(f):
        reg.salvar()
        sinal = c.sinal()
        print(f"{c.id}: +{campo.value}={f.valor}  | status confirmado: {c.status.rotulo}"
              + (f" | sinal não confirmado: {sinal.valor.rotulo}" if sinal else ""))
    else:
        print(f"{c.id}: fato já registrado (mesmo campo, valor e URL)")
    return 0


def cmd_importar_pci(a) -> int:
    reg = _registro(a)
    areas = {Area(x) for x in a.areas.split(",")}
    total = 0
    for arq in a.arquivos:
        for linha in pci.importar(reg, Path(arq), areas):
            print(linha)
            total += 1
    reg.salvar()
    print(f"{total} alterações")
    return 0


def cmd_listar(a) -> int:
    reg = _registro(a)
    hoje = date.today()
    for c in sorted(reg.concursos.values(), key=lambda c: c.ultima_data, reverse=True):
        grupo, fase = c.grupo(hoje)
        if (a.area and c.area.value != a.area) or (a.grupo and grupo != a.grupo):
            continue
        banca = c.consolidar(Campo.BANCA)
        sinal = c.sinal()
        print(f"{c.id:<22} {c.area.value:<8} {fase:<22} "
              f"banca={(banca.valor if banca else '-')!s:<10} "
              f"{'sinal=' + sinal.valor.rotulo if sinal else ''}")
    return 0


def cmd_ver(a) -> int:
    import json

    c = _registro(a).obter(a.id)
    print(json.dumps(c.para_site(date.today()), ensure_ascii=False, indent=1))
    return 0


def cmd_validar(a) -> int:
    erros = _registro(a).validar()
    for e in erros:
        print("ERRO", e, file=sys.stderr)
    print(f"{len(erros)} erro(s)")
    return 1 if erros else 0


def cmd_site(a) -> int:
    print(f"Site gerado em {site.gerar(_registro(a), Path(a.saida))}")
    return 0


def cmd_conferir(a) -> int:
    """Fase 2: lê o DOU e sugere fatos OFICIAIS para concursos já registrados.

    Não grava nada: imprime os comandos `radar fato` para o curador revisar.
    """
    reg = _registro(a)
    ate = date.fromisoformat(a.ate) if a.ate else date.today()
    desde = ate - timedelta(days=a.dias - 1)
    d = desde
    while d <= ate:
        try:
            pubs = dou.coletar(d)
        except Exception as e:  # noqa: BLE001
            print(f"[DOU {d}] falhou: {e}", file=sys.stderr)
            pubs = []
        for pub in pubs:
            ev = classificar(pub)
            if not ev or not ev.tipo.status:
                continue
            conc = reg.ativo_por_sigla(ev.orgao.sigla)
            if not conc:
                print(f"# sem concurso registrado para {ev.orgao.sigla}: {ev.tipo.value} — {ev.titulo} {ev.url}")
                continue
            print(f"# {conc.id}: {ev.titulo}")
            print(f"python -m radar fato {conc.id} --campo status --valor {ev.tipo.status.value} "
                  f"--fonte-tipo oficial --veiculo DOU --url '{ev.url}' --data {ev.data}")
            if ev.banca and ev.tipo.status.ordem >= Status.BANCA_DEFINIDA.ordem:
                print(f"python -m radar fato {conc.id} --campo banca --valor '{ev.banca}' "
                      f"--fonte-tipo oficial --veiculo DOU --url '{ev.url}' --data {ev.data}")
        d += timedelta(days=1)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="radar", description="Radar de concursos (fiscal, controle, policial)")
    p.add_argument("--dados", default="data/concursos", help="diretório do registro")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("novo", help="cria um concurso (ID = SIGLA[-CARREIRA]-ANO)")
    n.add_argument("--sigla", required=True)
    n.add_argument("--ano", required=True, type=int, help="ano do 1º ato do ciclo (pedido/autorização)")
    n.add_argument("--carreira", help="sufixo opcional, ex.: ADM para PRF-ADM-2026")
    n.add_argument("--id", help="força um ID (evite)")
    n.add_argument("--orgao", required=True)
    n.add_argument("--area", required=True, choices=[x.value for x in Area])
    n.add_argument("--esfera", default="federal", choices=["federal", "estadual", "municipal"])
    n.add_argument("--uf")
    n.add_argument("--cargos", help="separados por ;")
    n.add_argument("--aliases", help="separados por ;")
    n.add_argument("--banca-anterior"), n.add_argument("--banca-anterior-ano", type=int)
    n.add_argument("--banca-anterior-url")
    n.set_defaults(f=cmd_novo)

    f = sub.add_parser("fato", help="registra um fato com fonte")
    f.add_argument("id")
    f.add_argument("--campo", required=True, choices=[x.value for x in Campo])
    f.add_argument("--valor", required=True)
    f.add_argument("--fonte-tipo", required=True, choices=[x.value for x in FonteTipo])
    f.add_argument("--veiculo", required=True)
    f.add_argument("--url", required=True)
    f.add_argument("--data", required=True, help="data do fato/publicação AAAA-MM-DD")
    f.add_argument("--nota")
    f.set_defaults(f=cmd_fato)

    i = sub.add_parser("importar-pci", help="importa JSON salvo do MCP da PCI Concursos")
    i.add_argument("arquivos", nargs="+")
    i.add_argument("--areas", default="fiscal,controle,policial")
    i.set_defaults(f=cmd_importar_pci)

    l = sub.add_parser("listar")
    l.add_argument("--area"), l.add_argument("--grupo")
    l.set_defaults(f=cmd_listar)

    v = sub.add_parser("ver", help="mostra o consolidado de um concurso")
    v.add_argument("id")
    v.set_defaults(f=cmd_ver)

    sub.add_parser("validar").set_defaults(f=cmd_validar)

    s = sub.add_parser("site")
    s.add_argument("--saida", default="docs")
    s.set_defaults(f=cmd_site)

    c = sub.add_parser("conferir", help="fase 2: sugere fatos oficiais a partir do DOU")
    c.add_argument("--dias", type=int, default=1), c.add_argument("--ate")
    c.set_defaults(f=cmd_conferir)

    k = sub.add_parser("classificar", help="classifica um ato do DOU colado (1ª linha = título)")
    k.add_argument("arquivo", nargs="?", default="-")
    k.set_defaults(f=cmd_classificar)

    a = p.parse_args(argv)
    try:
        return a.f(a)
    except (ErroRegistro, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2


def cmd_classificar(a) -> int:
    texto = sys.stdin.read() if a.arquivo == "-" else Path(a.arquivo).read_text(encoding="utf-8")
    titulo, _, corpo = texto.partition("\n")
    ev = classificar(Publicacao("manual", date.today().isoformat(), titulo, corpo, "-"))
    if not ev:
        print("Não classificado como ato de fase de concurso das áreas monitoradas.")
        return 1
    print(f"tipo={ev.tipo.value} orgao={ev.orgao.sigla} area={ev.area.value} banca={ev.banca} vagas={ev.vagas}")
    return 0
