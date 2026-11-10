import tempfile
import unittest
from pathlib import Path

from radar.fontes.pci_noticia import cargos_excluidos, extrair, importar_vagas
from radar.modelos import Area, Campo, Fato, FonteTipo
from radar.registro import Concurso, ErroRegistro, Registro

PAG = (Path(__file__).parent / "fixtures" / "pci_noticia.html").read_text(encoding="utf-8")
URL = "https://www.pciconcursos.com.br/noticias/exemplo"


def vc(cargo, vagas, cr=False, tipo=FonteTipo.AGREGADOR, veiculo="PCI Concursos", url=URL):
    return Fato(Campo.VAGAS_CARGO, {"cargo": cargo, "vagas": vagas, "cr": cr}, tipo, veiculo, url, "2026-11-10")


class TestExtrator(unittest.TestCase):
    def test_lista(self):
        linhas, banca = extrair(PAG)
        d = {l.cargo: (l.vagas, l.cr) for l in linhas}
        self.assertEqual(d["Auditor Fiscal da Receita Municipal"], (2, False))
        self.assertEqual(d["Fiscal de Tributos"], (0, True))
        self.assertEqual(d["Controlador Interno"], (1, True))
        self.assertEqual(d["Engenheiro Civil"], (0, True), "sem número + edital com CR = cadastro de reserva")
        self.assertEqual(banca, "Objetiva Concursos")

    def test_exclusao(self):
        self.assertIn("Analista Tributário", cargos_excluidos(PAG)[0])


class TestVagasArea(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = Registro(Path(self.tmp.name) / "c")
        self.c = self.reg.novo(Concurso("PREF-EXEMPLO-SP-2026", "Prefeitura de Exemplo/SP", "PREF-EXEMPLO-SP",
                                        Area.FISCAL, "municipal", "SP",
                                        cargos=["Auditor fiscal da receita municipal", "Fiscal de tributos",
                                                "Controlador interno", "Analista tributário"]))

    def tearDown(self):
        self.tmp.cleanup()

    def test_importacao_filtra_area_e_exclui_cargo(self):
        log = importar_vagas(self.c, PAG, URL, "2026-11-10")
        self.assertTrue(any("EXCLUÍDO" in x for x in log))
        self.assertNotIn("Analista tributário", self.c.cargos)
        va = self.c.vagas_area()
        cargos = {r["cargo"]: (r["vagas"], r["area"]) for r in va["cargos"]}
        self.assertNotIn("Soldador", cargos)
        self.assertNotIn("Agente Controlador de Zoonoses", cargos)
        self.assertNotIn("Agente Administrativo", cargos)
        self.assertEqual(cargos["Auditor Fiscal da Receita Municipal"], (2, "fiscal"))
        self.assertEqual(cargos["Controlador Interno"], (1, "controle"))
        self.assertEqual(va["cobertura"], "por_cargo")
        self.assertEqual(va["valor"], 3)  # 2 fiscal + 0 (CR) + 1 controle
        self.assertTrue(va["confirmado"])
        self.assertEqual(self.c.consolidar(Campo.BANCA).valor, "Objetiva Concursos")

    def test_parcial_e_sem_dado(self):
        self.assertEqual(self.c.vagas_area()["cobertura"], "sem_dado")
        self.c.adicionar(vc("Auditor Fiscal da Receita Municipal", 2))
        va = self.c.vagas_area()
        self.assertEqual(va["cobertura"], "parcial")
        self.assertFalse(va["confirmado"])
        self.assertIn("Fiscal de tributos", [p["cargo"] for p in va["pendentes"]])

    def test_so_cr(self):
        self.c.cargos = ["Fiscal de tributos"]
        self.c.adicionar(vc("Fiscal de Tributos", 0, cr=True))
        self.assertEqual(self.c.vagas_area()["cobertura"], "so_cr")

    def test_oficial_prevalece_e_imprensa_unica_nao_confirma(self):
        self.c.cargos = ["Auditor fiscal"]
        self.c.adicionar(vc("Auditor Fiscal", 3, tipo=FonteTipo.IMPRENSA, veiculo="Blog X", url="https://x.example/1"))
        self.assertFalse(self.c.vagas_area()["confirmado"])
        self.c.adicionar(vc("Auditor Fiscal", 2, tipo=FonteTipo.OFICIAL, veiculo="Edital", url="https://pref.example/edital.pdf"))
        va = self.c.vagas_area()
        self.assertEqual((va["valor"], va["confirmado"]), (2, True))

    def test_validacao(self):
        with self.assertRaises(ErroRegistro):
            self.c.adicionar(vc("Auditor Fiscal", 0, cr=False))
        with self.assertRaises(ErroRegistro):
            self.c.adicionar(Fato(Campo.VAGAS_CARGO, {"cargo": "", "vagas": 1}, FonteTipo.OFICIAL, "E", URL, "2026-11-10"))

    def test_persistencia(self):
        self.c.adicionar(vc("Auditor Fiscal da Receita Municipal", 2))
        self.reg.salvar()
        c2 = Registro(self.reg.dir).obter(self.c.id)
        self.assertEqual(c2.vagas_por_cargo()[0]["vagas"], 2)
        self.assertEqual(Registro(self.reg.dir).validar(), [])


if __name__ == "__main__":
    unittest.main()
