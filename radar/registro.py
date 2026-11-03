"""Registro de concursos: um arquivo JSON por concurso, com ID único.

ID = SIGLA[-CARREIRA]-ANO, ex.: RFB-2026, PRF-2026, PC-SP-2026, SEFAZ-MG-2026.
O ANO é o do primeiro ato do ciclo (pedido ou autorização; na falta deles, o
do edital) e NÃO muda depois, mesmo que o edital saia no ano seguinte. Nomes
alternativos ("Receita Federal 2027") vão em "aliases".

Cada concurso é só uma lista de FATOS com fonte. Status, banca, vagas etc.
são sempre recalculados a partir deles, com regras de confirmação:

* fonte oficial confirma qualquer campo;
* o PCI (agregador) confirma os dados do edital (ele só lista edital publicado);
* imprensa confirma quando 2+ veículos diferentes dizem o mesmo valor;
* fato de uma só fonte de imprensa aparece como "sinal", nunca como confirmado;
* banca "cotada" (especulação) nunca vira banca definida.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .modelos import CAMPOS_CONFIRMADOS_POR_AGREGADOR, Area, Campo, Fato, FonteTipo, Status

DIRETORIO = Path("data/concursos")
ID_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*-(\d{4})$")
ESFERAS = {"federal", "estadual", "municipal"}


class ErroRegistro(ValueError):
    pass


def gerar_id(sigla: str, ano: int | str, carreira: str | None = None) -> str:
    partes = [sigla] + ([carreira] if carreira else []) + [str(ano)]
    bruto = "-".join(partes).upper()
    return re.sub(r"-+", "-", re.sub(r"[^A-Z0-9]+", "-", _sem_acento(bruto))).strip("-")


def _sem_acento(t: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


@dataclass
class Consolidado:
    valor: object
    confirmado: bool
    fontes: list[Fato]
    divergentes: list[object] = field(default_factory=list)


@dataclass
class Concurso:
    id: str
    orgao: str
    sigla: str
    area: Area
    esfera: str = "federal"
    uf: str | None = None
    cargos: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    banca_anterior: dict | None = None   # {"nome": "FGV", "ano": 2022, "url": "..."}
    pci_ids: list[int] = field(default_factory=list)
    encerrado: bool = False
    fatos: list[Fato] = field(default_factory=list)

    # ---------------------------------------------------------------- escrita
    def adicionar(self, fato: Fato) -> bool:
        validar_fato(fato)
        if any(f.chave == fato.chave for f in self.fatos):
            return False
        fato.registrado_em = fato.registrado_em or date.today().isoformat()
        self.fatos.append(fato)
        return True

    # --------------------------------------------------------- consolidação
    def _do_campo(self, campo: Campo) -> list[Fato]:
        return sorted((f for f in self.fatos if f.campo is campo), key=lambda f: f.data)

    @staticmethod
    def _confirma(fato: Fato, todos: list[Fato]) -> bool:
        if fato.fonte_tipo is FonteTipo.OFICIAL:
            return True
        if fato.fonte_tipo is FonteTipo.AGREGADOR and fato.campo in CAMPOS_CONFIRMADOS_POR_AGREGADOR:
            return True
        veiculos = {f.veiculo.lower() for f in todos if str(f.valor) == str(fato.valor)}
        return len(veiculos) >= 2

    def consolidar(self, campo: Campo) -> Consolidado | None:
        fatos = self._do_campo(campo)
        if not fatos:
            return None
        if campo is Campo.STATUS:
            return self._consolidar_status(fatos)
        if campo in {Campo.BANCA_COTADA, Campo.NOTA, Campo.PREVISAO}:
            vals = list(dict.fromkeys(f.valor for f in reversed(fatos)))
            return Consolidado(vals, False, fatos)
        # escolhe o valor com melhor fonte; empate -> mais recente
        melhor = max(fatos, key=lambda f: (self._confirma(f, fatos), f.fonte_tipo.peso, f.data))
        topo = max(f.fonte_tipo.peso for f in fatos)
        divergentes = sorted({str(f.valor) for f in fatos
                              if f.fonte_tipo.peso == topo and str(f.valor) != str(melhor.valor)})
        apoio = [f for f in fatos if str(f.valor) == str(melhor.valor)]
        return Consolidado(melhor.valor, self._confirma(melhor, fatos), apoio, divergentes)

    def _consolidar_status(self, fatos: list[Fato]) -> Consolidado:
        def ordem(f):
            return Status(f.valor).ordem

        confirmados = [f for f in fatos if self._confirma(f, fatos)]
        if confirmados:
            topo = max(confirmados, key=ordem)
            apoio = [f for f in confirmados if f.valor == topo.valor]
            return Consolidado(Status(topo.valor), True, apoio)
        topo = max(fatos, key=ordem)
        return Consolidado(Status(topo.valor), False, [f for f in fatos if f.valor == topo.valor])

    def sinal(self) -> Consolidado | None:
        """Status mais avançado que só tem fonte única (ainda não confirmado)."""
        fatos = self._do_campo(Campo.STATUS)
        st = self.consolidar(Campo.STATUS)
        if not fatos or st is None:
            return None
        nao_conf = [f for f in fatos if not self._confirma(f, fatos)
                    and Status(f.valor).ordem > (st.valor.ordem if st.confirmado else -1)]
        if not nao_conf:
            return None
        topo = max(nao_conf, key=lambda f: Status(f.valor).ordem)
        return Consolidado(Status(topo.valor), False, [f for f in nao_conf if f.valor == topo.valor])

    @property
    def status(self) -> Status:
        st = self.consolidar(Campo.STATUS)
        if st and st.confirmado:
            return st.valor
        return Status.PREVISTO

    def _valor(self, campo: Campo):
        c = self.consolidar(campo)
        return c.valor if c else None

    def grupo(self, hoje: date) -> tuple[str, str]:
        if self.encerrado:
            return "encerrados", "Encerrado"
        st = self.status
        if st is Status.HOMOLOGADO:
            return "encerrados", "Homologado"
        if st is Status.EDITAL_PUBLICADO:
            ini, fim = self._valor(Campo.INSCRICOES_INICIO), self._valor(Campo.INSCRICOES_FIM)
            h = hoje.isoformat()
            if ini and h < ini:
                return "abertos", "Inscrições em breve"
            if fim and h <= fim:
                return "abertos", "Inscrições abertas"
            if fim and h > fim:
                return "andamento", "Inscrições encerradas"
            return "abertos", "Edital publicado"
        if st.ordem >= Status.COMISSAO_FORMADA.ordem:
            return "anunciados", st.rotulo
        if st is Status.AUTORIZADO:
            return "autorizados", st.rotulo
        return "previstos", st.rotulo

    @property
    def ultima_data(self) -> str:
        return max((f.data for f in self.fatos), default="")

    def para_site(self, hoje: date) -> dict:
        grupo, fase = self.grupo(hoje)

        def bloco(campo):
            c = self.consolidar(campo)
            if not c:
                return None
            return {"valor": c.valor.value if isinstance(c.valor, Status) else c.valor,
                    "confirmado": c.confirmado, "divergentes": c.divergentes,
                    "fontes": [{"veiculo": f.veiculo, "url": f.url, "data": f.data} for f in c.fontes]}

        sinal = self.sinal()
        return {
            "id": self.id, "orgao": self.orgao, "sigla": self.sigla, "area": self.area.value,
            "esfera": self.esfera, "uf": self.uf, "cargos": self.cargos, "aliases": self.aliases,
            "grupo": grupo, "fase": fase, "status": self.status.value, "status_rotulo": self.status.rotulo,
            "sinal": {"rotulo": sinal.valor.rotulo,
                      "fontes": [{"veiculo": f.veiculo, "url": f.url, "data": f.data} for f in sinal.fontes]}
                     if sinal else None,
            "banca": bloco(Campo.BANCA), "bancas_cotadas": self._valor(Campo.BANCA_COTADA) or [],
            "banca_anterior": self.banca_anterior,
            "vagas": bloco(Campo.VAGAS), "salario_max": bloco(Campo.SALARIO_MAX),
            "inscricoes_inicio": self._valor(Campo.INSCRICOES_INICIO),
            "inscricoes_fim": self._valor(Campo.INSCRICOES_FIM),
            "edital_url": self._valor(Campo.EDITAL_URL),
            "previsao": (self._valor(Campo.PREVISAO) or [None])[0],
            "atualizado_em": self.ultima_data,
            "linha_do_tempo": [
                {"data": f.data, "campo": f.campo.value, "valor": _rotulo_valor(f),
                 "fonte_tipo": f.fonte_tipo.value, "veiculo": f.veiculo, "url": f.url, "nota": f.nota}
                for f in sorted(self.fatos, key=lambda f: f.data, reverse=True)
            ],
        }

    # -------------------------------------------------------------- serial.
    def para_dict(self) -> dict:
        return {
            "id": self.id, "orgao": self.orgao, "sigla": self.sigla, "area": self.area.value,
            "esfera": self.esfera, "uf": self.uf, "cargos": self.cargos, "aliases": self.aliases,
            "banca_anterior": self.banca_anterior, "pci_ids": self.pci_ids, "encerrado": self.encerrado,
            "fatos": [f.para_dict() for f in sorted(self.fatos, key=lambda f: (f.data, f.campo.value))],
        }

    @classmethod
    def de_dict(cls, d: dict) -> "Concurso":
        d = dict(d)
        fatos = [Fato.de_dict(f) for f in d.pop("fatos", [])]
        return cls(area=Area(d.pop("area")), fatos=fatos, **d)


def _rotulo_valor(f: Fato) -> str:
    if f.campo is Campo.STATUS:
        return Status(f.valor).rotulo
    return str(f.valor)


def validar_fato(f: Fato) -> None:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", f.data or ""):
        raise ErroRegistro(f"data inválida: {f.data!r} (use AAAA-MM-DD)")
    if not (f.url or "").startswith(("http://", "https://")):
        raise ErroRegistro("todo fato precisa de URL da fonte (http/https)")
    if not f.veiculo.strip():
        raise ErroRegistro("informe o veículo/fonte")
    if f.campo is Campo.STATUS:
        Status(f.valor)  # levanta ValueError se inválido
    if f.campo in {Campo.VAGAS} and not isinstance(f.valor, int):
        raise ErroRegistro("vagas deve ser inteiro")
    if f.campo in {Campo.INSCRICOES_INICIO, Campo.INSCRICOES_FIM} and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(f.valor)):
        raise ErroRegistro("datas de inscrição em AAAA-MM-DD")


class Registro:
    def __init__(self, diretorio: Path = DIRETORIO):
        self.dir = Path(diretorio)
        self.concursos: dict[str, Concurso] = {}
        if self.dir.exists():
            for arq in sorted(self.dir.glob("*.json")):
                c = Concurso.de_dict(json.loads(arq.read_text(encoding="utf-8")))
                self.concursos[c.id] = c

    def novo(self, c: Concurso) -> Concurso:
        if not ID_RE.match(c.id):
            raise ErroRegistro(f"ID inválido {c.id!r}: use SIGLA[-CARREIRA]-ANO, ex. RFB-2026")
        if c.id in self.concursos:
            raise ErroRegistro(f"{c.id} já existe")
        if c.esfera not in ESFERAS:
            raise ErroRegistro(f"esfera inválida: {c.esfera}")
        self.concursos[c.id] = c
        return c

    def obter(self, id_ou_alias: str) -> Concurso:
        alvo = id_ou_alias.strip().upper()
        if alvo in self.concursos:
            return self.concursos[alvo]
        for c in self.concursos.values():
            if alvo in (a.upper() for a in c.aliases):
                return c
        raise ErroRegistro(f"concurso {id_ou_alias!r} não encontrado")

    def ativo_por_sigla(self, sigla: str, cargos: list[str] | None = None) -> Concurso | None:
        """Ciclo mais recente e não encerrado de um órgão (para casar fontes).

        Se o órgão tiver mais de um concurso ativo (ex.: SEFAZ-SP para analista
        e para auditor), escolhe pelo cargo; sem cargo em comum, não casa.
        """
        cands = [c for c in self.concursos.values()
                 if c.sigla.upper() == sigla.upper() and not c.encerrado and c.status is not Status.HOMOLOGADO]
        if cargos and any(c.cargos for c in cands):
            alvo = _palavras(cargos)
            # concurso sem cargos cadastrados aceita qualquer cargo (pontuação mínima 0)
            pontos = {c.id: (len(alvo & _palavras(c.cargos)) if c.cargos else 0) for c in cands}
            melhor = max(pontos.values())
            cands = [c for c in cands if pontos[c.id] == melhor and (melhor > 0 or not c.cargos)]
            if len(cands) > 1:
                return None
        return max(cands, key=lambda c: int(ID_RE.match(c.id).group(1)), default=None)

    def salvar(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        for c in self.concursos.values():
            (self.dir / f"{c.id}.json").write_text(
                json.dumps(c.para_dict(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def validar(self) -> list[str]:
        erros = []
        for c in self.concursos.values():
            if not ID_RE.match(c.id):
                erros.append(f"{c.id}: ID inválido")
            for f in c.fatos:
                try:
                    validar_fato(f)
                except (ErroRegistro, ValueError) as e:
                    erros.append(f"{c.id}: {e}")
        return erros


def _palavras(cargos: list[str]) -> set[str]:
    texto = _sem_acento(" ".join(cargos)).lower()
    return {p for p in re.findall(r"[a-z]{4,}", texto)
            if p not in {"cargo", "cargos", "nivel", "area", "classe", "para", "publicas"}}
