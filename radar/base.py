"""Base de dados do radar (JSON versionado no git) e consolidação dos concursos.

Cada concurso guarda apenas os eventos (atos oficiais) que o compõem; os campos
"status", "banca", "vagas"... são sempre recalculados a partir deles. Assim o
histórico fica auditável e uma regra nova de classificação pode ser
reaplicada sem perder nada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .modelos import Area, Evento, Status, TipoEvento

ARQUIVO = Path("data/radar.json")
JANELA_CICLO_DIAS = 3 * 365  # um evento a mais de 3 anos do último inicia um novo ciclo


@dataclass
class Concurso:
    chave: str
    orgao_chave: str
    eventos: list[Evento] = field(default_factory=list)

    # ---- campos consolidados -------------------------------------------
    @property
    def _ordenados(self) -> list[Evento]:
        return sorted(self.eventos, key=lambda e: e.data)

    @property
    def orgao(self):
        return self._ordenados[-1].orgao

    @property
    def area(self) -> Area:
        return self._ordenados[-1].area

    @property
    def status(self) -> Status:
        status = [e.tipo.status for e in self.eventos if e.tipo.status]
        return max(status, key=lambda s: s.ordem) if status else Status.PREVISTO

    @property
    def situacao(self) -> str | None:
        """'cancelado' / 'suspenso' quando o ato mais recente for desse tipo."""
        for e in reversed(self._ordenados):
            if e.tipo is TipoEvento.CANCELAMENTO:
                return "cancelado"
            if e.tipo is TipoEvento.SUSPENSAO:
                return "suspenso"
            if e.tipo in {TipoEvento.EDITAL_ABERTURA, TipoEvento.RETIFICACAO, TipoEvento.HOMOLOGACAO}:
                return None
        return None

    def _ultimo(self, atributo: str, tipos: set[TipoEvento] | None = None):
        for e in reversed(self._ordenados):
            if (tipos is None or e.tipo in tipos) and getattr(e, atributo):
                return getattr(e, atributo)
        return None

    @property
    def banca(self) -> str | None:
        return self._ultimo("banca")

    @property
    def vagas(self) -> int | None:
        return self._ultimo("vagas", {TipoEvento.EDITAL_ABERTURA, TipoEvento.RETIFICACAO}) or self._ultimo("vagas")

    @property
    def salario_max(self) -> float | None:
        valores = [e.salario_max for e in self.eventos if e.salario_max]
        return max(valores) if valores else None

    @property
    def inscricoes(self) -> tuple[str | None, str | None]:
        edit = {TipoEvento.EDITAL_ABERTURA, TipoEvento.RETIFICACAO}
        return self._ultimo("inscricoes_inicio", edit), self._ultimo("inscricoes_fim", edit)

    @property
    def cargos(self) -> list[str]:
        vistos: list[str] = []
        for e in self._ordenados:
            vistos += [c for c in e.cargos if c not in vistos]
        return vistos

    @property
    def ultima_data(self) -> str:
        return self._ordenados[-1].data

    def grupo(self, hoje: date) -> tuple[str, str]:
        """(grupo, rótulo da fase) – como o candidato enxerga o concurso hoje."""
        if self.situacao == "cancelado":
            return "encerrados", "Cancelado"
        if self.situacao == "suspenso":
            return "anunciados", "Suspenso"
        st = self.status
        if st is Status.HOMOLOGADO:
            return "encerrados", "Homologado"
        if st is Status.EDITAL_PUBLICADO:
            ini, fim = self.inscricoes
            h = hoje.isoformat()
            if ini and h < ini:
                return "abertos", "Inscrições em breve"
            if fim and h <= fim:
                return "abertos", "Inscrições abertas"
            if fim and h > fim:
                return "andamento", "Inscrições encerradas"
            return "abertos", "Edital publicado"
        if st in {Status.COMISSAO_FORMADA, Status.BANCA_DEFINIDA, Status.BANCA_CONTRATADA}:
            return "anunciados", st.rotulo
        if st is Status.AUTORIZADO:
            return "autorizados", st.rotulo
        return "previstos", st.rotulo

    def para_site(self, hoje: date) -> dict:
        grupo, fase = self.grupo(hoje)
        ini, fim = self.inscricoes
        o = self.orgao
        return {
            "chave": self.chave,
            "orgao": o.nome,
            "sigla": o.sigla,
            "esfera": o.esfera,
            "uf": o.uf,
            "area": self.area.value,
            "status": self.status.value,
            "status_rotulo": self.status.rotulo,
            "situacao": self.situacao,
            "grupo": grupo,
            "fase": fase,
            "banca": self.banca,
            "vagas": self.vagas,
            "salario_max": self.salario_max,
            "inscricoes_inicio": ini,
            "inscricoes_fim": fim,
            "cargos": self.cargos,
            "atualizado_em": self.ultima_data,
            "eventos": [
                {"data": e.data, "tipo": e.tipo.value, "tipo_rotulo": e.tipo.rotulo,
                 "titulo": e.titulo, "url": e.url, "fonte": e.fonte}
                for e in reversed(self._ordenados)
            ],
        }


class Base:
    def __init__(self, caminho: Path = ARQUIVO):
        self.caminho = Path(caminho)
        self.concursos: dict[str, Concurso] = {}
        if self.caminho.exists():
            bruto = json.loads(self.caminho.read_text(encoding="utf-8"))
            for c in bruto.get("concursos", []):
                self.concursos[c["chave"]] = Concurso(
                    c["chave"], c["orgao_chave"], [Evento.de_dict(e) for e in c["eventos"]]
                )

    @property
    def ids(self) -> set[str]:
        return {e.id for c in self.concursos.values() for e in c.eventos}

    def adicionar(self, ev: Evento) -> bool:
        """Insere o evento no concurso certo. Retorna False se já existia."""
        if ev.id in self.ids:
            return False
        alvo = self._ciclo_aberto(ev)
        if alvo is None:
            ano = ev.data[:4]
            chave = f"{ev.orgao.chave}-{ano}"
            n = 2
            while chave in self.concursos:
                chave, n = f"{ev.orgao.chave}-{ano}-{n}", n + 1
            alvo = self.concursos[chave] = Concurso(chave, ev.orgao.chave)
        alvo.eventos.append(ev)
        return True

    def _ciclo_aberto(self, ev: Evento) -> Concurso | None:
        candidatos = [c for c in self.concursos.values() if c.orgao_chave == ev.orgao.chave]
        for c in sorted(candidatos, key=lambda c: c.ultima_data, reverse=True):
            encerrado = c.status is Status.HOMOLOGADO or c.situacao == "cancelado"
            distancia = abs((date.fromisoformat(ev.data) - date.fromisoformat(c.ultima_data)).days)
            if distancia > JANELA_CICLO_DIAS:
                continue
            # depois de homologado, só aceita atos posteriores à homologação
            # se forem do próprio ciclo (resultado/retificação); um novo
            # pedido/autorização abre outro concurso.
            if encerrado and ev.tipo.status and ev.tipo.status.ordem < Status.EDITAL_PUBLICADO.ordem:
                continue
            return c
        return None

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        dados = {
            "versao": 1,
            "concursos": [
                {"chave": c.chave, "orgao_chave": c.orgao_chave,
                 "eventos": [e.para_dict() for e in sorted(c.eventos, key=lambda e: e.data)]}
                for c in sorted(self.concursos.values(), key=lambda c: c.chave)
            ],
        }
        self.caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
