import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from radar import site
from radar.base import Base
from radar.fontes import dou
from radar.modelos import Area, Evento, Orgao, Status, TipoEvento

FIXTURE = Path(__file__).parent / "fixtures" / "dou_leiturajornal.html"


def ev(tipo, data, sigla="RFB", **kw):
    return Evento(tipo=tipo, data=data, titulo=f"{tipo.value} {data}", url=f"https://x/{tipo.value}/{data}",
                  fonte="DOU", orgao=Orgao("Receita Federal do Brasil", sigla, Area.FISCAL), area=Area.FISCAL, **kw)


class TestBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.base = Base(Path(self.dir.name) / "radar.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_ciclo_e_status(self):
        b = self.base
        b.adicionar(ev(TipoEvento.AUTORIZACAO, "2026-03-01", vagas=500))
        b.adicionar(ev(TipoEvento.COMISSAO, "2026-04-01"))
        b.adicionar(ev(TipoEvento.CONTRATO_BANCA, "2026-06-01", banca="FGV"))
        self.assertEqual(len(b.concursos), 1)
        c = next(iter(b.concursos.values()))
        self.assertEqual(c.status, Status.BANCA_CONTRATADA)
        self.assertEqual(c.banca, "FGV")
        self.assertEqual(c.grupo(date(2026, 7, 1)), ("anunciados", "Banca contratada"))

        b.adicionar(ev(TipoEvento.EDITAL_ABERTURA, "2026-10-01", vagas=600,
                       inscricoes_inicio="2026-10-10", inscricoes_fim="2026-11-10"))
        self.assertEqual(c.vagas, 600)
        self.assertEqual(c.grupo(date(2026, 10, 5))[1], "Inscrições em breve")
        self.assertEqual(c.grupo(date(2026, 11, 3))[1], "Inscrições abertas")
        self.assertEqual(c.grupo(date(2026, 12, 1))[0], "andamento")

    def test_evento_duplicado(self):
        e = ev(TipoEvento.AUTORIZACAO, "2026-03-01")
        self.assertTrue(self.base.adicionar(e))
        self.assertFalse(self.base.adicionar(e))

    def test_novo_ciclo_apos_homologacao(self):
        b = self.base
        b.adicionar(ev(TipoEvento.EDITAL_ABERTURA, "2024-01-10"))
        b.adicionar(ev(TipoEvento.HOMOLOGACAO, "2024-09-10"))
        b.adicionar(ev(TipoEvento.AUTORIZACAO, "2026-05-01"))
        self.assertEqual(sorted(b.concursos), ["rfb-2024", "rfb-2026"])

    def test_cancelamento(self):
        b = self.base
        b.adicionar(ev(TipoEvento.EDITAL_ABERTURA, "2026-01-10"))
        b.adicionar(ev(TipoEvento.CANCELAMENTO, "2026-02-10"))
        c = next(iter(b.concursos.values()))
        self.assertEqual(c.grupo(date(2026, 3, 1)), ("encerrados", "Cancelado"))

    def test_persistencia_e_site(self):
        self.base.adicionar(ev(TipoEvento.AUTORIZACAO, "2026-03-01", vagas=500))
        self.base.salvar()
        recarregada = Base(self.base.caminho)
        self.assertEqual(len(recarregada.concursos), 1)
        saida = Path(self.dir.name) / "docs"
        site.gerar(recarregada, saida, date(2026, 11, 3))
        dados = json.loads((saida / "concursos.json").read_text(encoding="utf-8"))
        self.assertEqual(dados["concursos"][0]["grupo"], "autorizados")
        self.assertIn("Radar de Concursos", (saida / "index.html").read_text(encoding="utf-8"))
        self.assertIn("<rss", (saida / "feed.xml").read_text(encoding="utf-8"))


class TestDOU(unittest.TestCase):
    def test_parse_leitura(self):
        itens = dou.parse_leitura(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(itens), 2)
        p = dou.para_publicacao(itens[0], date(2026, 11, 3))
        self.assertEqual(p.data, "2026-11-03")
        self.assertTrue(p.url.endswith("/web/dou/-/portaria-mgi-n-9.999-exemplo"))
        self.assertIn("Receita Federal", p.texto)

    def test_parse_integra(self):
        html = '<html><div class="texto-dou"><p>Art. 1º Autorizar o <b>concurso</b>.</p></div><div>rodapé</div>'
        self.assertEqual(dou.parse_integra(html).strip(), "Art. 1º Autorizar o concurso .")


if __name__ == "__main__":
    unittest.main()
