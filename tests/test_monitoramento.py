import json
import tempfile
import unittest
from pathlib import Path

from radar.fontes import pci
from radar.modelos import Area
from radar.monitoramento import Alvo, BuscaPCI, Monitoramento
from radar.registro import Concurso, Registro


class TestMonitoramento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arq = Path(self.tmp.name) / "monitoramento.json"
        self.arq.write_text(json.dumps({"buscas_padrao": {
            "pci": [{"ferramenta": "buscar_por_cargo", "termo": "auditor fiscal", "uf": None}],
            "web": ["concurso SEFAZ banca definida"]}, "alvos": []}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pedido_vira_alvo_e_entra_no_plano(self):
        m = Monitoramento(self.arq)
        a = m.adicionar(Alvo("", "SEFAZ-SP – Analista", "fiscal", "SP",
                             pci=[BuscaPCI("pesquisar_concursos", "sefaz", "SP"),
                                  BuscaPCI("buscar_por_cargo", "auditor fiscal")],
                             web=["concurso Sefaz SP analista"], origem="issue #1"))
        self.assertEqual(a.id, "M001")
        m.salvar()
        m2 = Monitoramento(self.arq)
        plano = m2.plano([("RFB-2026", "Receita Federal 2026")])
        termos = [b.descrever() for b in plano["pci"]]
        self.assertIn('pesquisar_concursos(termo="sefaz", uf="sp")', termos)
        self.assertEqual(len(termos), 2, "busca repetida deve ser deduplicada")
        self.assertIn("concurso Sefaz SP analista", plano["web"])
        self.assertIn("concurso Receita Federal 2026 banca edital", plano["web"])

    def test_validacoes(self):
        m = Monitoramento(self.arq)
        with self.assertRaises(ValueError):
            m.adicionar(Alvo("", "Sem buscas", "fiscal"))
        with self.assertRaises(ValueError):
            m.adicionar(Alvo("", "Área errada", "saude", web=["x"]))
        m.adicionar(Alvo("", "PC-MG", "policial", web=["concurso pc mg"]))
        with self.assertRaises(ValueError):
            m.adicionar(Alvo("", "pc-mg", "policial", web=["outra"]))
        with self.assertRaises(ValueError):
            BuscaPCI("listar_tudo", "x")


class TestDesambiguacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = Registro(Path(self.tmp.name) / "c")
        self.reg.novo(Concurso("SEFAZ-SP-APOFP-2026", "SEFAZ-SP", "SEFAZ-SP", Area.FISCAL,
                               cargos=["Analista em Planejamento, Orçamento e Finanças Públicas"]))

    def tearDown(self):
        self.tmp.cleanup()

    def _pci(self, cargos):
        arq = Path(self.tmp.name) / "p.json"
        arq.write_text(json.dumps({"meta": {"data_atual": "2026-11-03", "endpoint": "pesquisa"}, "data": [
            {"id": 1, "titulo": "SEFAZ - Secretaria da Fazenda e Planejamento", "uf": "SP", "cargos": cargos,
             "cargos_total": len(cargos), "vagas_salario": "10 vagas", "datas": {"inicio": "2026-12-01"},
             "noticia": {"link": "https://pci.example/1"}}]}), encoding="utf-8")
        return pci.importar(self.reg, arq)

    def test_mesmo_cargo_casa(self):
        self._pci(["ANALISTA EM PLANEJAMENTO, ORÇAMENTO E FINANÇAS PÚBLICAS - TI"])
        self.assertEqual(set(self.reg.concursos), {"SEFAZ-SP-APOFP-2026"})

    def test_outro_cargo_nao_mistura(self):
        self._pci(["AGENTE FISCAL DE RENDAS"])
        self.assertIn("SEFAZ-SP-2026", self.reg.concursos)
        self.assertEqual(len(self.reg.obter("SEFAZ-SP-APOFP-2026").fatos), 0)


if __name__ == "__main__":
    unittest.main()
