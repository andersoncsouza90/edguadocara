"""Modelos de dados do Radar de Concursos."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum


class Area(str, Enum):
    FISCAL = "fiscal"
    CONTROLE = "controle"
    POLICIAL = "policial"


class Status(str, Enum):
    """Ciclo de vida de um concurso, em ordem de avanço.

    A ordem importa: o status consolidado de um concurso é sempre o mais
    avançado entre os eventos encontrados (o status nunca "regride").
    """

    PREVISTO = "previsto"                  # citado em LOA/PLOA, LDO, plano anual, declaração oficial
    SOLICITADO = "solicitado"              # pedido de autorização enviado (ex.: ao MGI)
    AUTORIZADO = "autorizado"              # portaria/lei/ato autorizando o concurso
    COMISSAO_FORMADA = "comissao_formada"  # portaria de comissão organizadora
    BANCA_DEFINIDA = "banca_definida"      # dispensa/contratação direta ratificada
    BANCA_CONTRATADA = "banca_contratada"  # extrato de contrato com a banca
    EDITAL_PUBLICADO = "edital_publicado"  # edital de abertura publicado
    HOMOLOGADO = "homologado"              # resultado final homologado

    @property
    def ordem(self) -> int:
        return list(Status).index(self)

    @property
    def rotulo(self) -> str:
        return ROTULOS_STATUS[self]


ROTULOS_STATUS = {
    Status.PREVISTO: "Previsto",
    Status.SOLICITADO: "Solicitado",
    Status.AUTORIZADO: "Autorizado",
    Status.COMISSAO_FORMADA: "Comissão formada",
    Status.BANCA_DEFINIDA: "Banca definida",
    Status.BANCA_CONTRATADA: "Banca contratada",
    Status.EDITAL_PUBLICADO: "Edital publicado",
    Status.HOMOLOGADO: "Homologado",
}


class TipoEvento(str, Enum):
    PREVISAO = "previsao"
    SOLICITACAO = "solicitacao"
    AUTORIZACAO = "autorizacao"
    COMISSAO = "comissao"
    BANCA_DEFINIDA = "banca_definida"
    CONTRATO_BANCA = "contrato_banca"
    EDITAL_ABERTURA = "edital_abertura"
    RETIFICACAO = "retificacao"
    SUSPENSAO = "suspensao"
    CANCELAMENTO = "cancelamento"
    RESULTADO = "resultado"
    HOMOLOGACAO = "homologacao"

    @property
    def status(self) -> Status | None:
        """Status que o evento comprova (None = não altera o status)."""
        return STATUS_POR_TIPO.get(self)

    @property
    def rotulo(self) -> str:
        return ROTULOS_TIPO[self]


STATUS_POR_TIPO = {
    TipoEvento.PREVISAO: Status.PREVISTO,
    TipoEvento.SOLICITACAO: Status.SOLICITADO,
    TipoEvento.AUTORIZACAO: Status.AUTORIZADO,
    TipoEvento.COMISSAO: Status.COMISSAO_FORMADA,
    TipoEvento.BANCA_DEFINIDA: Status.BANCA_DEFINIDA,
    TipoEvento.CONTRATO_BANCA: Status.BANCA_CONTRATADA,
    TipoEvento.EDITAL_ABERTURA: Status.EDITAL_PUBLICADO,
    # retificar um edital pressupõe que ele já foi publicado
    TipoEvento.RETIFICACAO: Status.EDITAL_PUBLICADO,
    TipoEvento.RESULTADO: Status.EDITAL_PUBLICADO,
    TipoEvento.HOMOLOGACAO: Status.HOMOLOGADO,
}

ROTULOS_TIPO = {
    TipoEvento.PREVISAO: "Previsão",
    TipoEvento.SOLICITACAO: "Solicitação de autorização",
    TipoEvento.AUTORIZACAO: "Autorização",
    TipoEvento.COMISSAO: "Comissão organizadora",
    TipoEvento.BANCA_DEFINIDA: "Banca definida (contratação direta)",
    TipoEvento.CONTRATO_BANCA: "Contrato com a banca",
    TipoEvento.EDITAL_ABERTURA: "Edital de abertura",
    TipoEvento.RETIFICACAO: "Retificação de edital",
    TipoEvento.SUSPENSAO: "Suspensão",
    TipoEvento.CANCELAMENTO: "Cancelamento",
    TipoEvento.RESULTADO: "Resultado final",
    TipoEvento.HOMOLOGACAO: "Homologação",
}


@dataclass
class Orgao:
    nome: str
    sigla: str
    area: Area | None = None
    esfera: str = "federal"  # federal | estadual | municipal
    uf: str | None = None

    @property
    def chave(self) -> str:
        from .classificador import slug

        return slug(self.sigla or self.nome)


@dataclass
class Publicacao:
    """Ato bruto vindo de uma fonte (DOU, diário municipal, cadastro manual)."""

    fonte: str
    data: str  # AAAA-MM-DD
    titulo: str
    texto: str
    url: str
    hierarquia: str = ""        # ex.: "Ministério da Fazenda/Secretaria Especial da Receita Federal"
    uf: str | None = None
    municipio: str | None = None


@dataclass
class Evento:
    tipo: TipoEvento
    data: str
    titulo: str
    url: str
    fonte: str
    orgao: Orgao
    area: Area
    resumo: str = ""
    banca: str | None = None
    vagas: int | None = None
    salario_max: float | None = None
    inscricoes_inicio: str | None = None
    inscricoes_fim: str | None = None
    cargos: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        base = f"{self.url}|{self.titulo}|{self.tipo.value}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    def para_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        d["tipo"] = self.tipo.value
        d["area"] = self.area.value
        d["orgao"]["area"] = self.orgao.area.value if self.orgao.area else None
        return d

    @classmethod
    def de_dict(cls, d: dict) -> "Evento":
        o = dict(d["orgao"])
        o["area"] = Area(o["area"]) if o.get("area") else None
        campos = {k: v for k, v in d.items() if k not in {"id", "orgao", "tipo", "area"}}
        return cls(tipo=TipoEvento(d["tipo"]), area=Area(d["area"]), orgao=Orgao(**o), **campos)


def hoje_iso() -> str:
    return date.today().isoformat()
