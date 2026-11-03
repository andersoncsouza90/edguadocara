"""Modelos de dados do Radar de Concursos."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Area(str, Enum):
    FISCAL = "fiscal"
    CONTROLE = "controle"
    POLICIAL = "policial"


class Status(str, Enum):
    """Fases de um concurso, em ordem de avanço (o status nunca regride)."""

    PREVISTO = "previsto"                      # LOA/PLOA, plano anual, declaração oficial
    SOLICITADO = "solicitado"                  # pedido de autorização enviado (ex.: ao MGI)
    AUTORIZADO = "autorizado"                  # portaria/ato autorizando o concurso
    COMISSAO_FORMADA = "comissao_formada"      # comissão organizadora instituída
    BANCA_EM_DEFINICAO = "banca_em_definicao"  # processo de contratação da banca em curso
    BANCA_DEFINIDA = "banca_definida"          # banca escolhida (dispensa ratificada, anúncio oficial)
    BANCA_CONTRATADA = "banca_contratada"      # contrato assinado / extrato publicado
    EDITAL_PUBLICADO = "edital_publicado"      # edital de abertura publicado
    HOMOLOGADO = "homologado"                  # resultado final homologado

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
    Status.BANCA_EM_DEFINICAO: "Banca em contratação",
    Status.BANCA_DEFINIDA: "Banca definida",
    Status.BANCA_CONTRATADA: "Banca contratada",
    Status.EDITAL_PUBLICADO: "Edital publicado",
    Status.HOMOLOGADO: "Homologado",
}


class FonteTipo(str, Enum):
    """Hierarquia de confiabilidade das fontes."""

    OFICIAL = "oficial"      # DOU/DOE, site do órgão, ofício, processo SEI
    AGREGADOR = "agregador"  # PCI Concursos (lista concursos com edital publicado)
    IMPRENSA = "imprensa"    # sites especializados (Folha Dirigida, Estratégia, Gran, JC...)

    @property
    def peso(self) -> int:
        return {"oficial": 3, "agregador": 2, "imprensa": 1}[self.value]


class Campo(str, Enum):
    STATUS = "status"
    BANCA = "banca"                    # só banca DEFINIDA/CONTRATADA
    BANCA_COTADA = "banca_cotada"      # especulação / favorita / em negociação
    VAGAS = "vagas"
    SALARIO_MAX = "salario_max"
    INSCRICOES_INICIO = "inscricoes_inicio"
    INSCRICOES_FIM = "inscricoes_fim"
    EDITAL_URL = "edital_url"
    PREVISAO = "previsao"              # texto livre: "edital previsto para dezembro"
    NOTA = "nota"                      # andamento relevante sem mudar campos


# Campos em que o PCI (agregador) basta para confirmar: ele só lista
# concursos depois que o edital sai.
CAMPOS_CONFIRMADOS_POR_AGREGADOR = {
    Campo.STATUS, Campo.VAGAS, Campo.SALARIO_MAX, Campo.INSCRICOES_INICIO,
    Campo.INSCRICOES_FIM, Campo.EDITAL_URL, Campo.BANCA,
}


@dataclass
class Fato:
    """Uma afirmação sobre um concurso, sempre amarrada à fonte."""

    campo: Campo
    valor: str | int | float
    fonte_tipo: FonteTipo
    veiculo: str
    url: str
    data: str                 # data do fato/publicação da fonte (AAAA-MM-DD)
    registrado_em: str = ""
    nota: str = ""

    @property
    def chave(self) -> tuple:
        return (self.campo.value, str(self.valor), self.url)

    def para_dict(self) -> dict:
        d = asdict(self)
        d["campo"] = self.campo.value
        d["fonte_tipo"] = self.fonte_tipo.value
        return d

    @classmethod
    def de_dict(cls, d: dict) -> "Fato":
        d = dict(d)
        return cls(campo=Campo(d.pop("campo")), fonte_tipo=FonteTipo(d.pop("fonte_tipo")), **d)


# ---------------------------------------------------------------------------
# Modelos usados pela conferência no Diário Oficial (fase 2)
# ---------------------------------------------------------------------------

class TipoEvento(str, Enum):
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
    SOLICITACAO = "solicitacao"

    @property
    def status(self) -> Status | None:
        return {
            TipoEvento.SOLICITACAO: Status.SOLICITADO,
            TipoEvento.AUTORIZACAO: Status.AUTORIZADO,
            TipoEvento.COMISSAO: Status.COMISSAO_FORMADA,
            TipoEvento.BANCA_DEFINIDA: Status.BANCA_DEFINIDA,
            TipoEvento.CONTRATO_BANCA: Status.BANCA_CONTRATADA,
            TipoEvento.EDITAL_ABERTURA: Status.EDITAL_PUBLICADO,
            TipoEvento.HOMOLOGACAO: Status.HOMOLOGADO,
        }.get(self)


@dataclass
class Orgao:
    nome: str
    sigla: str
    area: Area | None = None
    esfera: str = "federal"  # federal | estadual | municipal
    uf: str | None = None


@dataclass
class Publicacao:
    """Ato bruto vindo de um diário oficial."""

    fonte: str
    data: str
    titulo: str
    texto: str
    url: str
    hierarquia: str = ""
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
