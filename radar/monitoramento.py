"""Lista de monitoramento: o que a curadoria diária PRECISA buscar.

data/monitoramento.json guarda:
* "buscas_padrao": buscas que rodam todo dia (PCI e web), por área;
* "alvos": pedidos de inclusão ("monitorem a SEFAZ-SP para analista"),
  cada um com as próprias buscas e os concursos já vinculados.

Um pedido vira um alvo permanente: mesmo que ainda não exista concurso, as
buscas dele rodam todos os dias até que o alvo seja encerrado.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

ARQUIVO = Path("data/monitoramento.json")
FERRAMENTAS_PCI = {"pesquisar_concursos", "buscar_por_cargo"}


@dataclass
class BuscaPCI:
    ferramenta: str          # pesquisar_concursos | buscar_por_cargo
    termo: str
    uf: str | None = None

    def __post_init__(self):
        if self.ferramenta not in FERRAMENTAS_PCI:
            raise ValueError(f"ferramenta PCI inválida: {self.ferramenta}")
        if self.uf:
            self.uf = self.uf.lower()

    @property
    def chave(self):
        return (self.ferramenta, self.termo.lower(), self.uf or "")

    def descrever(self) -> str:
        arg = "cargo" if self.ferramenta == "buscar_por_cargo" else "termo"
        uf = f', uf="{self.uf}"' if self.uf else ""
        return f'{self.ferramenta}({arg}="{self.termo}"{uf})'


@dataclass
class Alvo:
    id: str
    descricao: str
    area: str
    uf: str | None = None
    pci: list[BuscaPCI] = field(default_factory=list)
    web: list[str] = field(default_factory=list)
    concursos: list[str] = field(default_factory=list)
    origem: str = ""          # "issue #12", "chat", "curadoria"
    solicitado_em: str = ""
    situacao: str = "ativo"   # ativo | encerrado
    nota: str = ""


class Monitoramento:
    def __init__(self, caminho: Path = ARQUIVO):
        self.caminho = Path(caminho)
        bruto = json.loads(self.caminho.read_text(encoding="utf-8")) if self.caminho.exists() else {}
        pad = bruto.get("buscas_padrao", {})
        self.padrao_pci = [BuscaPCI(**b) for b in pad.get("pci", [])]
        self.padrao_web = list(pad.get("web", []))
        self.alvos: list[Alvo] = []
        for a in bruto.get("alvos", []):
            a = dict(a)
            pci = [BuscaPCI(**b) for b in a.pop("pci", [])]
            self.alvos.append(Alvo(pci=pci, **a))

    def proximo_id(self) -> str:
        nums = [int(m.group(1)) for a in self.alvos if (m := re.match(r"M(\d+)$", a.id))]
        return f"M{(max(nums) if nums else 0) + 1:03d}"

    def obter(self, id_alvo: str) -> Alvo:
        for a in self.alvos:
            if a.id.upper() == id_alvo.upper():
                return a
        raise ValueError(f"alvo {id_alvo} não encontrado")

    def adicionar(self, alvo: Alvo) -> Alvo:
        if not alvo.pci and not alvo.web:
            raise ValueError("informe ao menos uma busca (--pci-termo, --pci-cargo ou --web)")
        if alvo.area not in {"fiscal", "controle", "policial"}:
            raise ValueError("área deve ser fiscal, controle ou policial")
        duplicado = next((a for a in self.alvos if a.situacao == "ativo"
                          and a.descricao.lower() == alvo.descricao.lower()), None)
        if duplicado:
            raise ValueError(f"já existe o alvo {duplicado.id} com essa descrição")
        alvo.id = alvo.id or self.proximo_id()
        alvo.solicitado_em = alvo.solicitado_em or date.today().isoformat()
        self.alvos.append(alvo)
        return alvo

    def plano(self, concursos_sem_edital: list[tuple[str, str]]) -> dict:
        """Lista deduplicada do que buscar hoje."""
        pci, vistos = [], set()
        for b in self.padrao_pci + [b for a in self.alvos if a.situacao == "ativo" for b in a.pci]:
            if b.chave not in vistos:
                vistos.add(b.chave)
                pci.append(b)
        web = list(dict.fromkeys(
            self.padrao_web
            + [w for a in self.alvos if a.situacao == "ativo" for w in a.web]
            + [f"concurso {nome} banca edital" for _, nome in concursos_sem_edital]
        ))
        return {"pci": pci, "web": web}

    def salvar(self) -> None:
        dados = {
            "buscas_padrao": {"pci": [asdict(b) for b in self.padrao_pci], "web": self.padrao_web},
            "alvos": [asdict(a) for a in self.alvos],
        }
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
