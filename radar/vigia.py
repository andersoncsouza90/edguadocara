"""Vigia: detecção de novidades direto nas fontes oficiais.

Roda sem IA, várias vezes ao dia (GitHub Actions e a rotina de curadoria):

1. baixa as listagens das fontes de data/fontes.json (sites de bancas, DOU);
2. guarda só os itens das três áreas (órgão ou cargo no título);
3. compara com o que já foi visto e gera a FILA DE NOVIDADES.

A curadoria (agente) trata cada novidade: confere na fonte, registra os fatos
com `radar fato --fonte-tipo oficial` e marca com `radar tratar`.

Arquivos (nenhum é escrito pelos dois lados, para não haver conflito no git):
  data/vigia/detectados.json  escrito só pelo vigia
  data/vigia/saude.json       escrito só pelo vigia (cada fonte: ok/erro)
  data/vigia/tratados.json    escrito só pela curadoria
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .classificador import classificar, identificar_orgao, normalizar
from .fontes import http_get
from .fontes.pci import CARGOS_AREA

FONTES = Path("data/fontes.json")
DIR = Path("data/vigia")
RETENCAO_DIAS = 120

# Palavras que, no título de uma listagem de banca, indicam uma das 3 áreas.
_SINAIS = [
    ("fiscal", r"\bsefaz\b|\bsefin\b|secretaria (?:de estado |municipal )?(?:da |de )?(?:fazenda|financas|economia|receita|tributacao)"
               r"|receita (?:federal|estadual|municipal)|\bfisco\b|tributari[oa]"),
    ("controle", r"tribunal de contas|\btc[eum]\b|controladoria|\bcg[eum]\b|controle (?:interno|externo)"),
    ("policial", r"policia (?:civil|militar|penal|federal|rodoviaria|cientifica|legislativa)|\bp[cm][- /]?[a-z]{2}\b"
                 r"|brigada militar|seguranca publica|administracao penitenciaria"),
]
_IGNORAR = re.compile(r"vestibular|residencia|exame de suficiencia|processo seletivo simplificado|estagi")


@dataclass
class Item:
    fonte: str
    veiculo: str
    titulo: str
    url: str
    area: str
    orgao: str | None = None
    tipo: str | None = None       # fase sugerida (DOU) ou situação na banca
    detalhe: str = ""
    primeiro_visto: str = ""

    @property
    def id(self) -> str:
        return hashlib.sha1(f"{self.fonte}|{self.url}|{normalizar(self.titulo)}".encode()).hexdigest()[:12]


def relevancia(titulo: str) -> tuple[str, str | None] | None:
    """(área, sigla do órgão) se o título for de uma das três áreas."""
    n = normalizar(titulo)
    if _IGNORAR.search(n):
        return None
    org = identificar_orgao(n)
    if org and org.area:
        return org.area.value, org.sigla
    for area, padrao in CARGOS_AREA:
        if re.search(padrao, n):
            return area.value, None
    for area, padrao in _SINAIS:
        if re.search(padrao, n):
            return area, None
    return None


def _antigo(titulo: str, url: str, hoje: date) -> bool:
    """Página de concurso de 2+ anos atrás (ex.: .../rfb22, "Cabo PM 2022"): não é novidade."""
    anos = [int(a) for a in re.findall(r"\b(20\d{2})\b", titulo)]
    m = re.search(r"(?<!\d)(20\d{2}|\d{2})/?(?:index\.html)?$", url.rstrip("/"))
    if m:
        a = int(m.group(1))
        anos.append(a if a > 2000 else 2000 + a)
    anos = [a for a in anos if 2010 <= a <= hoje.year + 1]
    return bool(anos) and max(anos) <= hoje.year - 2


# ------------------------------------------------------------------ coletores

def _texto(trecho: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", trecho))).strip()


def _html_links(f: dict) -> list[tuple[str, str, str]]:
    pagina = http_get(f["url"], tentativas=2)
    padrao = re.compile(f.get("padrao_link", "."))
    vistos, itens = set(), []
    for href, miolo in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', pagina, re.S | re.I):
        titulo = _texto(miolo)
        url = urllib.parse.urljoin(f["url"], html.unescape(href))
        if len(titulo) < 8 or not padrao.search(url) or url in vistos:
            continue
        vistos.add(url)
        itens.append((titulo, url, ""))
    return itens


def _json_lista(f: dict) -> list[tuple[str, str, str]]:
    itens = []
    for situacao, url in f["urls"].items():
        for d in json.loads(http_get(url, tentativas=2)):
            titulo = str(d.get(f.get("campo_titulo", "nome"), "")).strip()
            if not titulo:
                continue
            detalhe = "; ".join(f"{rot}: {d[c]}" for rot, c in f.get("campos_detalhe", {}).items() if d.get(c) not in (None, ""))
            link = f["url_item"].format(id=d.get("id", ""))
            itens.append((titulo, link, f"{situacao}; {detalhe}" if detalhe else situacao))
    return itens


_DOU_TIPOS = re.compile(r"edital|extrato de contrato|dispensa|inexigibilidade|contratacao direta|homologa")


def _dou(f: dict, hoje: date) -> list[Item]:
    """Atos de fase de concurso no DOU.

    O resumo da listagem tem ~400 caracteres e quase nunca cita "concurso".
    Então: (a) classifica pelo resumo os atos que citam concurso; (b) baixa a
    íntegra só dos atos de órgãos do catálogo (RFB, PF, PRF, TCU, CGU...) cujo
    tipo interessa (edital, contrato, dispensa), uma única vez por ato.
    """
    from .fontes import dou
    from .modelos import Publicacao

    lidos = _ler("dou_lidos.json")
    itens, total = [], 0
    for dia in (hoje - timedelta(days=1), hoje):
        for secao in f.get("secoes", ("do1", "do3")):
            pagina = http_get(f"{dou.BASE}/leiturajornal", {"data": f"{dia:%d-%m-%Y}", "secao": secao}, tentativas=2)
            for ato in dou.parse_leitura(pagina):
                total += 1
                pub = dou.para_publicacao(ato, dia)
                cab = normalizar(f"{pub.titulo} {ato.get('artType', '')}")
                do_catalogo = identificar_orgao(normalizar(f"{pub.titulo} {pub.hierarquia}")) is not None
                cita = "concurso" in normalizar(pub.texto) or "concurso" in cab
                if not cita and not (do_catalogo and _DOU_TIPOS.search(cab)):
                    continue
                if do_catalogo and ato.get("urlTitle"):
                    if pub.url in lidos:            # íntegra já lida em execução anterior
                        continue
                    try:
                        pub = dou.para_publicacao(ato, dia, dou.parse_integra(http_get(pub.url, tentativas=2)))
                    except Exception:  # noqa: BLE001 - fica com o resumo
                        pass
                    lidos[pub.url] = dia.isoformat()
                ev = classificar(pub)
                if ev is None or ev.orgao.sigla == ev.orgao.nome:   # só órgãos do catálogo
                    continue
                itens.append(Item(f["id"], f["veiculo"], ev.titulo, ev.url, ev.area.value, ev.orgao.sigla,
                                  ev.tipo.value, re.sub(r"\s+", " ", pub.texto)[:300]))
    limite = (hoje - timedelta(days=10)).isoformat()
    _gravar("dou_lidos.json", {u: d for u, d in lidos.items() if d >= limite})
    f["_total"] = total
    return itens


def coletar_fonte(f: dict, hoje: date) -> tuple[list[Item], int]:
    """(itens relevantes, total de itens lidos)."""
    if f["tipo"] == "dou":
        itens = _dou(f, hoje)
        return itens, f.pop("_total", 0)
    brutos = _html_links(f) if f["tipo"] == "html_links" else _json_lista(f)
    relevantes = []
    for titulo, url, detalhe in brutos:
        r = relevancia(titulo)
        if r and not _antigo(titulo, url, hoje):
            relevantes.append(Item(f["id"], f["veiculo"], titulo[:240], url, r[0], r[1], None, detalhe))
    return relevantes, len(brutos)


# ------------------------------------------------------------------ estado

def hoje_brasil() -> date:
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date()


def _ler(nome: str) -> dict:
    p = DIR / nome
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _gravar(nome: str, dados: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def vigiar(hoje: date | None = None, so: list[str] | None = None) -> tuple[list[Item], dict]:
    """Coleta todas as fontes; devolve (itens novos, saúde das fontes)."""
    hoje = hoje or hoje_brasil()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    fontes = [f for f in json.loads(FONTES.read_text(encoding="utf-8")) if f.get("ativa", True) and (not so or f["id"] in so)]
    detectados, saude, novos = _ler("detectados.json"), _ler("saude.json"), []
    for f in fontes:
        anterior = saude.get(f["id"], {})
        try:
            itens, total = coletar_fonte(f, hoje)
            if total == 0:
                raise RuntimeError("a página respondeu, mas nenhum item foi lido (layout mudou?)")
            saude[f["id"]] = {"nome": f["nome"], "ok": True, "ultima_ok": agora, "lidos": total, "relevantes": len(itens), "erro": ""}
        except Exception as e:  # noqa: BLE001 - uma fonte fora do ar não derruba as outras
            saude[f["id"]] = {"nome": f["nome"], "ok": False, "ultima_ok": anterior.get("ultima_ok", ""),
                              "lidos": 0, "relevantes": 0, "erro": str(e)[:200], "falhou_em": agora}
            continue
        for it in itens:
            if it.id not in detectados:
                it.primeiro_visto = agora
                detectados[it.id] = asdict(it)
                novos.append(it)
            else:
                detectados[it.id]["visto_em"] = agora
    limite = (hoje - timedelta(days=RETENCAO_DIAS)).isoformat()
    detectados = {k: v for k, v in detectados.items() if (v.get("visto_em") or v["primeiro_visto"])[:10] >= limite}
    _gravar("detectados.json", detectados)
    _gravar("saude.json", saude)
    return novos, saude


def pendentes() -> list[dict]:
    tratados = _ler("tratados.json")
    fila = [dict(v, id=k) for k, v in _ler("detectados.json").items() if k not in tratados]
    return sorted(fila, key=lambda v: v["primeiro_visto"], reverse=True)


def tratar(ids: list[str], resultado: str, concurso: str | None = None, nota: str = "") -> int:
    detectados, tratados = _ler("detectados.json"), _ler("tratados.json")
    n = 0
    for i in ids:
        if i not in detectados:
            raise ValueError(f"novidade {i} não existe")
        tratados[i] = {"em": date.today().isoformat(), "resultado": resultado, "concurso": concurso, "nota": nota}
        n += 1
    tratados = {k: v for k, v in tratados.items() if k in detectados}
    _gravar("tratados.json", tratados)
    return n


def saude() -> dict:
    return _ler("saude.json")
