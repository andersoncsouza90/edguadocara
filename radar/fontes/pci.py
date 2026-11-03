"""Importa resultados do MCP da PCI Concursos para o registro.

O MCP só é acessível ao agente (Claude). O agente salva o JSON retornado
pelas ferramentas (pesquisar_concursos, buscar_por_cargo, listar_concursos)
num arquivo e roda:  python -m radar importar-pci arquivo.json

Regras para não misturar concursos:
* o órgão é identificado SÓ pelo título do concurso no PCI (+ UF); a busca do
  PCI é ampla ("receita federal" devolve universidades e prefeituras);
* prefeituras/câmaras só entram se tiverem cargo típico de fiscal/controle,
  e vagas/salário só são registrados se TODOS os cargos do edital forem da
  área (senão o "11 vagas até R$ 7.660" seria do edital inteiro, não do cargo).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..classificador import ESTADOS, identificar_orgao, normalizar
from ..modelos import Area, Campo, Fato, FonteTipo, Status
from ..registro import Concurso, Registro, gerar_id

UF_PARA_NOME = {uf: nome for nome, uf in ESTADOS.items()}

CARGOS_AREA: list[tuple[Area, str]] = [
    (Area.FISCAL, r"auditor[- ]fiscal|fiscal (?:de |da )?(?:tributos|rendas?|receita)|fiscal tributario"
                  r"|agente fiscal de (?:tributos|rendas)|auditor (?:de |da )?(?:tributos|receita)|analista tributario"),
    (Area.CONTROLE, r"controle (?:interno|externo)|controlador|auditor de controle|analista de controle"
                    r"|financas e controle"),
    (Area.POLICIAL, r"delegado|agente de policia|escrivao|investigador|papiloscopista|perito criminal"
                    r"|policial|soldado|oficial (?:pm|combatente)|cadete"),
]


@dataclass
class ItemPCI:
    id: int
    titulo: str
    uf: str | None
    cargos: list[str]
    cargos_total: int
    vagas_salario: str
    inicio: str | None
    fim: str | None
    link: str
    parcial: bool = False  # buscar_por_cargo: "cargos" traz só os que casaram


def ler(caminho: Path) -> tuple[str, list[ItemPCI]]:
    bruto = json.loads(Path(caminho).read_text(encoding="utf-8"))
    meta = bruto.get("meta") or {}
    hoje = meta.get("data_atual")
    parcial = meta.get("endpoint") == "cargo"
    itens = []
    for d in bruto.get("data") or []:
        datas = d.get("datas") or {}
        itens.append(ItemPCI(
            id=int(d["id"]), titulo=d.get("titulo", ""), uf=d.get("uf"),
            cargos=d.get("cargos") or [], cargos_total=d.get("cargos_total") or len(d.get("cargos") or []),
            vagas_salario=d.get("vagas_salario") or "", inicio=datas.get("inicio"), fim=datas.get("fim"),
            link=(d.get("noticia") or {}).get("link") or "",
            parcial=parcial or len(d.get("cargos") or []) < (d.get("cargos_total") or 0),
        ))
    return hoje, itens


def cargos_da_area(cargos: list[str]) -> dict[Area, list[str]]:
    achados: dict[Area, list[str]] = {}
    for cargo in cargos:
        n = normalizar(cargo)
        for area, padrao in CARGOS_AREA:
            if re.search(padrao, n):
                achados.setdefault(area, []).append(cargo.strip().capitalize())
                break
    return achados


def _vagas_salario(texto: str) -> tuple[int | None, float | None]:
    n = normalizar(texto)
    v = re.search(r"(\d[\d.]*)\s+vagas?", n)
    s = re.search(r"r\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})", n)
    return (int(v.group(1).replace(".", "")) if v else None,
            float(s.group(1).replace(".", "").replace(",", ".")) if s else None)


def identificar(item: ItemPCI):
    """Retorna (sigla, nome, area, esfera, uf, cargos_relevantes, todos_relevantes) ou None."""
    sufixo = f" de {UF_PARA_NOME[item.uf]}" if item.uf in UF_PARA_NOME else ""
    org = identificar_orgao(normalizar(item.titulo + sufixo))
    por_area = cargos_da_area(item.cargos)
    if org and org.area:
        # órgão inteiro da área (PF, PM, TCE...): todos os cargos contam
        cargos = [c.strip().capitalize() for c in item.cargos]
        return (org.sigla, org.nome, org.area, org.esfera, org.uf or item.uf, cargos, not item.parcial)
    t = normalizar(item.titulo)
    m = re.search(r"\b(prefeitura|camara)(?: e [a-z ]+?)?(?: municipal)? (?:de|do|da) (.+)$", t)
    if por_area and m:
        area = next(a for a in (Area.FISCAL, Area.CONTROLE, Area.POLICIAL) if a in por_area)
        relevantes = [c for a in por_area for c in por_area[a]]
        prefixo = "CAM" if m.group(1) == "camara" else "PREF"
        cidade = m.group(2)
        original = re.sub(r"\s+", " ", item.titulo).strip()
        cidade_nome = original[-len(cidade):] if normalizar(original[-len(cidade):]) == cidade else cidade.title()
        sigla = re.sub(r"[^A-Z0-9]+", "-", f"{prefixo} {cidade} {item.uf or ''}".upper()).strip("-")
        nome = f"{'Câmara Municipal' if prefixo == 'CAM' else 'Prefeitura'} de {cidade_nome}" + \
            (f"/{item.uf}" if item.uf else "")
        return (sigla, nome, area, "municipal", item.uf, relevantes,
                not item.parcial and len(relevantes) == item.cargos_total)
    return None


def importar(registro: Registro, caminho: Path, areas: set[Area] | None = None) -> list[str]:
    hoje, itens = ler(caminho)
    log = []
    for it in itens:
        ident = identificar(it)
        if not ident:
            continue
        sigla, nome, area, esfera, uf, relevantes, todos = ident
        if areas and area not in areas:
            continue
        conc = next((c for c in registro.concursos.values() if it.id in c.pci_ids), None) \
            or registro.ativo_por_sigla(sigla, it.cargos)
        if conc is None:
            ano = (it.inicio or hoje or "")[:4]
            novo_id = gerar_id(sigla, ano)
            if novo_id in registro.concursos:
                # mesmo órgão/ano, cargos diferentes: não adivinha, pede curadoria
                log.append(f"AMBÍGUO: PCI {it.id} ({it.titulo}: {', '.join(it.cargos[:3])}) — "
                           f"{novo_id} já existe com outros cargos; crie com --carreira e reimporte")
                continue
            conc = registro.novo(Concurso(novo_id, nome, sigla, area, esfera, uf, relevantes))
            log.append(f"novo concurso {conc.id} ({nome})")
        if it.id not in conc.pci_ids:
            conc.pci_ids.append(it.id)
        for cargo in relevantes:
            if cargo not in conc.cargos:
                conc.cargos.append(cargo)

        def fato(campo, valor, nota=""):
            if valor is None or not it.link:
                return
            if conc.adicionar(Fato(campo, valor, FonteTipo.AGREGADOR, "PCI Concursos", it.link, hoje, nota=nota)):
                log.append(f"{conc.id}: {campo.value} = {valor}")

        fato(Campo.STATUS, Status.EDITAL_PUBLICADO.value)
        fato(Campo.INSCRICOES_INICIO, it.inicio)
        fato(Campo.INSCRICOES_FIM, it.fim)
        if todos:  # só quando o edital é inteiro da área
            vagas, salario = _vagas_salario(it.vagas_salario)
            fato(Campo.VAGAS, vagas)
            fato(Campo.SALARIO_MAX, salario)
        elif it.vagas_salario and not it.parcial:
            fato(Campo.NOTA, f"Edital com {it.cargos_total} cargos ({it.vagas_salario} no total); "
                             f"cargos da área: {', '.join(relevantes)}")
    return log

