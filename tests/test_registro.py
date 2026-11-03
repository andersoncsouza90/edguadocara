import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from radar import site
from radar.fontes import dou, pci
from radar.modelos import Area, Campo, Fato, FonteTipo, Status
from radar.registro import Concurso, ErroRegistro, Registro, gerar_id

FIX = Path(__file__).parent / "fixtures"


def fato(campo, valor, tipo=FonteTipo.IMPRENSA, veiculo="Veículo A", url="https://a.example/1", data="2026-10-20"):
    return Fato(campo, valor, tipo, veiculo, url, data)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = Registro(Path(self.tmp.name) / "concursos")
        self.rfb = self.reg.novo(Concurso("RFB-2026", "Receita Federal do Brasil", "RFB", Area.FISCAL,
                                          banca_anterior={"nome": "FGV", "ano": 2022}))

    def tearDown(self):
        self.tmp.cleanup()


class TestIds(Base):
    def test_gerar_id(self):
        self.assertEqual(gerar_id("rfb", 2026), "RFB-2026")
        self.assertEqual(gerar_id("PRF", 2026, "adm"), "PRF-ADM-2026")
        self.assertEqual(gerar_id("SEFAZ-SP", 2026), "SEFAZ-SP-2026")

    def test_id_invalido_e_duplicado(self):
        with self.assertRaises(ErroRegistro):
            self.reg.novo(Concurso("Receita 2026", "x", "RFB", Area.FISCAL))
        with self.assertRaises(ErroRegistro):
            self.reg.novo(Concurso("RFB-2026", "x", "RFB", Area.FISCAL))

    def test_alias(self):
        self.rfb.aliases.append("RECEITA-FEDERAL-2027")
        self.assertIs(self.reg.obter("receita-federal-2027"), self.rfb)

    def test_fato_sem_fonte_e_recusado(self):
        with self.assertRaises(ErroRegistro):
            self.rfb.adicionar(fato(Campo.BANCA, "FGV", url=""))


class TestConfirmacao(Base):
    def test_oficial_confirma(self):
        self.rfb.adicionar(fato(Campo.STATUS, "autorizado", FonteTipo.OFICIAL, "DOU", "https://in.gov.br/x", "2026-07-03"))
        self.assertEqual(self.rfb.status, Status.AUTORIZADO)

    def test_imprensa_unica_vira_sinal_e_nao_status(self):
        self.rfb.adicionar(fato(Campo.STATUS, "autorizado", FonteTipo.OFICIAL, "DOU", "https://in.gov.br/x", "2026-07-03"))
        self.rfb.adicionar(fato(Campo.STATUS, "banca_definida"))
        self.assertEqual(self.rfb.status, Status.AUTORIZADO)
        self.assertEqual(self.rfb.sinal().valor, Status.BANCA_DEFINIDA)

    def test_duas_imprensas_confirmam(self):
        self.rfb.adicionar(fato(Campo.STATUS, "banca_em_definicao", veiculo="Folha Dirigida"))
        self.rfb.adicionar(fato(Campo.STATUS, "banca_em_definicao", veiculo="Gran", url="https://b.example/2"))
        self.assertEqual(self.rfb.status, Status.BANCA_EM_DEFINICAO)
        self.assertIsNone(self.rfb.sinal())

    def test_mesmo_veiculo_duas_vezes_nao_confirma(self):
        self.rfb.adicionar(fato(Campo.STATUS, "banca_contratada", veiculo="Gran", url="https://b.example/1"))
        self.rfb.adicionar(fato(Campo.STATUS, "banca_contratada", veiculo="gran", url="https://b.example/2"))
        self.assertNotEqual(self.rfb.status, Status.BANCA_CONTRATADA)

    def test_banca_cotada_nunca_vira_banca(self):
        self.rfb.adicionar(fato(Campo.BANCA_COTADA, "FGV"))
        self.rfb.adicionar(fato(Campo.BANCA_COTADA, "FGV", veiculo="B", url="https://b.example/2"))
        self.assertIsNone(self.rfb.consolidar(Campo.BANCA))
        d = self.rfb.para_site(date(2026, 11, 3))
        self.assertIsNone(d["banca"])
        self.assertEqual(d["bancas_cotadas"], ["FGV"])
        self.assertEqual(d["banca_anterior"]["nome"], "FGV")

    def test_divergencia_de_vagas(self):
        self.rfb.adicionar(fato(Campo.VAGAS, 146, veiculo="A"))
        self.rfb.adicionar(fato(Campo.VAGAS, 146, veiculo="B", url="https://b.example/2"))
        self.rfb.adicionar(fato(Campo.VAGAS, 150, veiculo="C", url="https://c.example/3"))
        v = self.rfb.consolidar(Campo.VAGAS)
        self.assertEqual((v.valor, v.confirmado, v.divergentes), (146, True, ["150"]))

    def test_oficial_prevalece_sobre_imprensa(self):
        self.rfb.adicionar(fato(Campo.VAGAS, 200, veiculo="A"))
        self.rfb.adicionar(fato(Campo.VAGAS, 146, FonteTipo.OFICIAL, "DOU", "https://in.gov.br/x", "2026-07-03"))
        self.assertEqual(self.rfb.consolidar(Campo.VAGAS).valor, 146)

    def test_grupos(self):
        self.rfb.adicionar(fato(Campo.STATUS, "edital_publicado", FonteTipo.AGREGADOR, "PCI Concursos"))
        self.rfb.adicionar(fato(Campo.INSCRICOES_INICIO, "2026-12-01", FonteTipo.AGREGADOR, "PCI Concursos"))
        self.rfb.adicionar(fato(Campo.INSCRICOES_FIM, "2026-12-20", FonteTipo.AGREGADOR, "PCI Concursos"))
        self.assertEqual(self.rfb.grupo(date(2026, 11, 3)), ("abertos", "Inscrições em breve"))
        self.assertEqual(self.rfb.grupo(date(2026, 12, 5)), ("abertos", "Inscrições abertas"))
        self.assertEqual(self.rfb.grupo(date(2027, 1, 5))[0], "andamento")


class TestPCI(Base):
    def test_importacao(self):
        log = pci.importar(self.reg, FIX / "pci_pesquisa.json")
        ids = set(self.reg.concursos)
        self.assertIn("PC-PE-2026", ids)
        self.assertIn("CGU-2026", ids)
        self.assertIn("PREF-LAGOA-SANTA-MG-2026", ids)
        self.assertFalse(any("UFMG" in i for i in ids), "universidade não pode entrar")
        pe = self.reg.obter("PC-PE-2026")
        self.assertEqual(pe.consolidar(Campo.VAGAS).valor, 500)  # edital inteiro é policial
        self.assertEqual(pe.status, Status.EDITAL_PUBLICADO)
        lagoa = self.reg.obter("PREF-LAGOA-SANTA-MG-2026")
        self.assertIsNone(lagoa.consolidar(Campo.VAGAS), "79 vagas são do edital todo, não do cargo fiscal")
        self.assertEqual(lagoa.cargos, ["Auditor fiscal da receita municipal"])
        self.assertTrue(log)

    def test_reimportar_nao_duplica_e_casa_com_existente(self):
        cgu = self.reg.novo(Concurso("CGU-2025", "Controladoria-Geral da União", "CGU", Area.CONTROLE))
        pci.importar(self.reg, FIX / "pci_pesquisa.json")
        n = len(cgu.fatos)
        pci.importar(self.reg, FIX / "pci_pesquisa.json")
        self.assertNotIn("CGU-2026", self.reg.concursos)
        self.assertEqual(len(cgu.fatos), n)


class TestPersistenciaSite(Base):
    def test_salvar_carregar_e_site(self):
        self.rfb.adicionar(fato(Campo.STATUS, "autorizado", FonteTipo.OFICIAL, "DOU", "https://in.gov.br/x", "2026-07-03"))
        self.reg.salvar()
        reg2 = Registro(self.reg.dir)
        self.assertEqual(reg2.obter("RFB-2026").status, Status.AUTORIZADO)
        self.assertEqual(reg2.validar(), [])
        saida = Path(self.tmp.name) / "docs"
        site.gerar(reg2, saida, date(2026, 11, 3))
        dados = json.loads((saida / "concursos.json").read_text(encoding="utf-8"))
        self.assertEqual(dados["concursos"][0]["grupo"], "autorizados")
        self.assertIn("<rss", (saida / "feed.xml").read_text(encoding="utf-8"))


class TestDOU(unittest.TestCase):
    def test_parse_leitura(self):
        itens = dou.parse_leitura((FIX / "dou_leiturajornal.html").read_text(encoding="utf-8"))
        self.assertEqual(len(itens), 2)
        p = dou.para_publicacao(itens[0], date(2026, 11, 3))
        self.assertTrue(p.url.endswith("/web/dou/-/portaria-mgi-n-9.999-exemplo"))


if __name__ == "__main__":
    unittest.main()
