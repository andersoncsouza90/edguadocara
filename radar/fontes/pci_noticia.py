"""Vagas por cargo a partir da página de notícia da PCI Concursos.

O MCP da PCI só informa o total do edital ("84 vagas no total, 38 cargos").
A notícia lista cada cargo, normalmente como itens <li>:

    Auditor Fiscal da Receita Municipal (1 vaga)
    Fiscal de Tributos (2 vagas + CR)
    Agente Fiscal (cadastro reserva)
    Engenheiro Civil                      <- sem número: cadastro de reserva,
                                             se a notícia disser que há CR

Também lê tabelas com coluna "Vagas". Só devolve o que conseguiu ler com
segurança; o resto fica pendente para a curadoria.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from ..classificador import detectar_banca, normalizar


@dataclass
class LinhaVaga:
    cargo: str
    vagas: int
    cr: bool
    nota: str = ""


def _texto(trecho: str) -> str:
    t = re.sub(r"<[^>]+>", " ", trecho)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def corpo(pagina: str) -> str:
    m = re.search(r'<div[^>]*itemprop="articleBody"[^>]*>(.*?)(?:<div class="(?:compartilh|sharelink|pciaudio)|</article>)',
                  pagina, re.S | re.I)
    return m.group(1) if m else pagina


_NUM_VAGAS = re.compile(r"(\d{1,3}(?:\.\d{3})*|\d+)\s*vagas?\b", re.I)
_CR = re.compile(r"(?i:cadastro\s+(?:de\s+)?reserva)|\bC\.?R\b")


def _linha(texto: str, ha_cr_no_edital: bool) -> LinhaVaga | None:
    texto = re.sub(r"\s*[–-]\s*R\$.*$", "", texto).strip()           # tira salário no fim
    if len(texto) > 160 or texto.endswith(".") or not texto:
        return None                                                     # frase, não item de lista
    n = _NUM_VAGAS.search(texto)
    cr = bool(_CR.search(texto))
    cargo = re.split(r"\s*[(:]|\s+[–-]\s+(?=\d|cadastro|CR)", texto, maxsplit=1)[0].strip(" -–:")
    if not cargo or len(cargo) < 3:
        return None
    if n:
        return LinhaVaga(cargo, int(n.group(1).replace(".", "")), cr)
    if cr:
        return LinhaVaga(cargo, 0, True)
    if ha_cr_no_edital and "(" not in texto:
        return LinhaVaga(cargo, 0, True, "sem número na lista da notícia: cadastro de reserva")
    return None


def extrair(pagina: str) -> tuple[list[LinhaVaga], str | None]:
    """(linhas por cargo, banca citada) a partir do HTML da notícia."""
    c = corpo(pagina)
    texto_todo = _texto(c)
    ha_cr = bool(_CR.search(texto_todo))
    linhas: list[LinhaVaga] = []

    for li in re.findall(r"<li[^>]*>(.*?)</li>", c, re.S | re.I):
        ln = _linha(_texto(li), ha_cr)
        if ln:
            linhas.append(ln)

    for tabela in re.findall(r"<table.*?</table>", c, re.S | re.I):
        linhas_tab = [[_texto(td) for td in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S | re.I)]
                      for tr in re.findall(r"<tr.*?</tr>", tabela, re.S | re.I)]
        if not linhas_tab:
            continue
        cab = [normalizar(x) for x in linhas_tab[0]]
        i_cargo = next((i for i, x in enumerate(cab) if "cargo" in x or "funcao" in x), None)
        i_vagas = next((i for i, x in enumerate(cab) if "vaga" in x), None)
        if i_cargo is None or i_vagas is None:
            continue
        for row in linhas_tab[1:]:
            if len(row) <= max(i_cargo, i_vagas):
                continue
            cargo, v = row[i_cargo].strip(), row[i_vagas]
            n = re.search(r"\d+", v.replace(".", ""))
            cr = bool(_CR.search(v))
            if cargo and (n or cr):
                linhas.append(LinhaVaga(cargo, int(n.group()) if n else 0, cr))

    # dedup por cargo (mantém a primeira ocorrência)
    vistos, unicas = set(), []
    for ln in linhas:
        k = normalizar(ln.cargo)
        if k not in vistos:
            vistos.add(k)
            unicas.append(ln)
    return unicas, detectar_banca(normalizar(texto_todo))


# ---------------------------------------------------------------------------
# Importação para o registro
# ---------------------------------------------------------------------------

def links_pci(concurso) -> list[str]:
    """Links de notícias do PCI já registrados para o concurso (mais recente primeiro)."""
    fatos = sorted((f for f in concurso.fatos if "pciconcursos.com.br/noticias/" in f.url),
                   key=lambda f: f.data, reverse=True)
    return list(dict.fromkeys(f.url for f in fatos))


def cargos_relevantes(concurso, linhas: list[LinhaVaga]) -> list[LinhaVaga]:
    """Órgão inteiro da área (PC, PM, SEFAZ...): todos os cargos. Prefeitura/câmara:
    só os cargos da área do radar ou já cadastrados no concurso."""
    from ..registro import _casa_cargo, _norm_cargo
    from .pci import CARGOS_AREA

    if concurso.esfera != "municipal":
        return linhas
    cadastrados = [_norm_cargo(c) for c in concurso.cargos]
    saida = []
    for ln in linhas:
        n = _norm_cargo(ln.cargo)
        if any(_casa_cargo(n, c) for c in cadastrados) or any(re.search(p, normalizar(ln.cargo)) for _, p in CARGOS_AREA):
            saida.append(ln)
    return saida


_EXCLUSAO = re.compile(r"exclu\w*\s+(?:o|os)\s+cargos?\s+(?:de\s+)?(.{3,400}?)(?:,?\s+bem como|\s+do concurso|\.)", re.I)


def cargos_excluidos(pagina: str) -> list[str]:
    """Trechos do tipo 'uma retificação excluiu o cargo de Fiscal de Tributos'."""
    texto = _texto(corpo(pagina))
    return [m.group(1) for m in _EXCLUSAO.finditer(texto)]


def importar_vagas(concurso, pagina: str, url: str, data: str) -> list[str]:
    from ..modelos import Campo, Fato, FonteTipo
    from ..registro import _casa_cargo, _norm_cargo

    log = []
    excluidos = " ; ".join(cargos_excluidos(pagina))
    if excluidos:
        ex = _norm_cargo(excluidos)
        da_area = [c for c in concurso.cargos if _casa_cargo(_norm_cargo(c), ex) or _norm_cargo(c) in ex]
        if da_area:
            concurso.adicionar(Fato(Campo.NOTA, f"Cargo(s) excluído(s) do edital por retificação/errata: {'; '.join(da_area)}",
                                    FonteTipo.AGREGADOR, "PCI Concursos", url, data))
            concurso.cargos = [c for c in concurso.cargos if c not in da_area]
            log.append(f"{concurso.id}: EXCLUÍDO(S) do edital: {'; '.join(da_area)}")
            if not concurso.cargos:
                concurso.encerrado = True
                log.append(f"{concurso.id}: nenhum cargo da área restante; concurso encerrado no radar")
                return log

    linhas, banca = extrair(pagina)
    relevantes = cargos_relevantes(concurso, linhas)
    if not relevantes:
        return [f"{concurso.id}: nenhum cargo da área com vagas legíveis em {url}"]
    for ln in relevantes:
        valor = {"cargo": ln.cargo, "vagas": ln.vagas, "cr": ln.cr}
        if concurso.adicionar(Fato(Campo.VAGAS_CARGO, valor, FonteTipo.AGREGADOR, "PCI Concursos", url, data, nota=ln.nota)):
            log.append(f"{concurso.id}: {ln.cargo} = {ln.vagas} vaga(s){' + CR' if ln.cr else ''}")
        if ln.cargo not in concurso.cargos and not any(normalizar(ln.cargo) == normalizar(c) for c in concurso.cargos):
            concurso.cargos.append(ln.cargo)
    if banca and not concurso.consolidar(Campo.BANCA):
        concurso.adicionar(Fato(Campo.BANCA, banca, FonteTipo.AGREGADOR, "PCI Concursos", url, data,
                                nota="banca citada na notícia do PCI"))
        log.append(f"{concurso.id}: banca = {banca}")
    return log
