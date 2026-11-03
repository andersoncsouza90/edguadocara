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
from .monitoramento import Alvo, BuscaPCI, Monitoramento
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


def _lista(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(";") if x.strip()]


def cmd_ajustar(a) -> int:
    reg = _registro(a)
    c = reg.obter(a.id)
    c.cargos += [x for x in _lista(a.add_cargo) if x not in c.cargos]
    c.aliases += [x.upper() for x in _lista(a.add_alias) if x.upper() not in c.aliases]
    if a.encerrar:
        c.encerrado = True
    reg.salvar()
    print(f"{c.id}: cargos={c.cargos} aliases={c.aliases} encerrado={c.encerrado}")
    return 0


def cmd_mon_adicionar(a) -> int:
    mon = Monitoramento(Path(a.monitoramento))
    pci = [BuscaPCI("pesquisar_concursos", t, a.uf) for t in _lista(a.pci_termo)]
    pci += [BuscaPCI("buscar_por_cargo", t, a.uf) for t in _lista(a.pci_cargo)]
    alvo = mon.adicionar(Alvo(id="", descricao=a.descricao, area=a.area, uf=(a.uf or "").upper() or None,
                              pci=pci, web=_lista(a.web), origem=a.origem or "", nota=a.nota or ""))
    mon.salvar()
    print(f"alvo {alvo.id} criado: {alvo.descricao}")
    return 0


def cmd_mon_listar(a) -> int:
    for alvo in Monitoramento(Path(a.monitoramento)).alvos:
        print(f"{alvo.id} [{alvo.situacao}] {alvo.descricao} ({alvo.area}, {alvo.uf or 'BR'}) "
              f"origem={alvo.origem or '-'} concursos={','.join(alvo.concursos) or '-'}")
    return 0


def cmd_mon_vincular(a) -> int:
    mon, reg = Monitoramento(Path(a.monitoramento)), _registro(a)
    alvo = mon.obter(a.alvo)
    cid = reg.obter(a.concurso).id
    if cid not in alvo.concursos:
        alvo.concursos.append(cid)
    mon.salvar()
    print(f"{alvo.id} -> {', '.join(alvo.concursos)}")
    return 0


def cmd_mon_encerrar(a) -> int:
    mon = Monitoramento(Path(a.monitoramento))
    alvo = mon.obter(a.alvo)
    alvo.situacao = "encerrado"
    alvo.nota = (alvo.nota + " | " if alvo.nota else "") + (a.motivo or "encerrado")
    mon.salvar()
    print(f"{alvo.id} encerrado")
    return 0


def cmd_mon_plano(a) -> int:
    """Imprime a lista de buscas do dia (o roteiro da curadoria)."""
    mon, reg = Monitoramento(Path(a.monitoramento)), _registro(a)
    sem_edital = [(c.id, f"{c.orgao} {'; '.join(c.cargos[:1])} {c.id.rsplit('-', 1)[1]}".strip())
                  for c in reg.concursos.values()
                  if not c.encerrado and c.status.ordem < Status.EDITAL_PUBLICADO.ordem]
    plano = mon.plano(sem_edital)
    print(f"# PCI ({len(plano['pci'])} chamadas) — salve cada retorno e rode `radar importar-pci`")
    for b in plano["pci"]:
        print(f"pci  {b.descrever()}")
    print(f"\n# Web ({len(plano['web'])} buscas) — registre fatos com `radar fato`")
    for w in plano["web"]:
        print(f"web  {w}")
    ativos = [x for x in mon.alvos if x.situacao == "ativo"]
    if ativos:
        print("\n# Alvos solicitados (confira se já há concurso e vincule com `radar monitorar vincular`)")
        for x in ativos:
            print(f"alvo {x.id}: {x.descricao} -> {', '.join(x.concursos) or 'SEM CONCURSO AINDA'}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="radar", description="Radar de concursos (fiscal, controle, policial)")
    p.add_argument("--dados", default="data/concursos", help="diretório do registro")
    p.add_argument("--monitoramento", default="data/monitoramento.json")
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

    aj = sub.add_parser("ajustar", help="adiciona cargos/aliases ou encerra um concurso")
    aj.add_argument("id")
    aj.add_argument("--add-cargo", help="separados por ;")
    aj.add_argument("--add-alias", help="separados por ;")
    aj.add_argument("--encerrar", action="store_true")
    aj.set_defaults(f=cmd_ajustar)

    m = sub.add_parser("monitorar", help="pedidos de inclusão e roteiro de buscas")
    msub = m.add_subparsers(dest="acao", required=True)
    ma = msub.add_parser("adicionar", help="registra um pedido de monitoramento")
    ma.add_argument("--descricao", required=True, help='ex.: "SEFAZ-SP – Analista (APOFP)"')
    ma.add_argument("--area", required=True, choices=[x.value for x in Area])
    ma.add_argument("--uf")
    ma.add_argument("--pci-termo", help="termos para pesquisar_concursos, separados por ;")
    ma.add_argument("--pci-cargo", help="termos para buscar_por_cargo, separados por ;")
    ma.add_argument("--web", help="buscas na web, separadas por ;")
    ma.add_argument("--origem", help='ex.: "issue #3", "chat"')
    ma.add_argument("--nota")
    ma.set_defaults(f=cmd_mon_adicionar)
    msub.add_parser("listar").set_defaults(f=cmd_mon_listar)
    mp = msub.add_parser("plano", help="roteiro de buscas do dia")
    mp.set_defaults(f=cmd_mon_plano)
    mv = msub.add_parser("vincular")
    mv.add_argument("alvo"), mv.add_argument("concurso")
    mv.set_defaults(f=cmd_mon_vincular)
    me = msub.add_parser("encerrar")
    me.add_argument("alvo"), me.add_argument("--motivo")
    me.set_defaults(f=cmd_mon_encerrar)

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
