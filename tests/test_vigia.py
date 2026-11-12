import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from radar import vigia

PAGINA = """<html><body>
<a href="/concursos/sefazxx26">Concurso Público para a Secretaria de Estado da Fazenda de Minas Gerais</a>
<a href="/concursos/pcxx26">Concurso Público para a Polícia Civil do Estado da Bahia</a>
<a href="/concursos/tjxx26">Concurso Público para o Tribunal de Justiça do Estado da Paraíba</a>
<a href="/concursos/macae">Concurso Público para a Prefeitura de Macaé</a>
<a href="/exames/cfc">Conselho Federal de Contabilidade - Exame de Suficiência</a>
<a href="/institucional">Sobre a instituição e seus programas</a>
</body></html>"""


class TestRelevancia(unittest.TestCase):
    def test_areas(self):
        self.assertEqual(vigia.relevancia("Concurso Público para a Receita Federal do Brasil"), ("fiscal", "RFB"))
        self.assertEqual(vigia.relevancia("Tribunal de Contas do Estado do Tocantins"), ("controle", "TCE-TO"))
        self.assertEqual(vigia.relevancia("Polícia Militar do Estado de São Paulo - Cabo PM")[0], "policial")
        self.assertEqual(vigia.relevancia("Prefeitura de X - Auditor Fiscal de Tributos")[0], "fiscal")

    def test_fora_do_escopo(self):
        for t in ["Tribunal de Justiça do Estado da Paraíba", "Prefeitura de Macaé", "UNASP Vestibular Medicina",
                  "Tribunal Regional do Trabalho da 6ª Região", "Residência Médica - Polícia Militar"]:
            self.assertIsNone(vigia.relevancia(t), t)


class TestVigia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.fontes = base / "fontes.json"
        self.fontes.write_text(json.dumps([
            {"id": "banca", "nome": "Banca X", "veiculo": "Banca X (site)", "tipo": "html_links",
             "url": "https://banca.example/concursos", "padrao_link": "/concursos/"},
            {"id": "fora", "nome": "Banca fora do ar", "veiculo": "Y", "tipo": "html_links", "url": "https://y.example/"},
        ]), encoding="utf-8")
        self.p = [mock.patch.object(vigia, "FONTES", self.fontes), mock.patch.object(vigia, "DIR", base / "vigia")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def _get(self, pagina):
        def fake(url, *a, **k):
            if "y.example" in url:
                raise RuntimeError("403")
            return pagina
        return mock.patch.object(vigia, "http_get", fake)

    def test_ciclo_completo(self):
        with self._get(PAGINA):
            novos, saude = vigia.vigiar(date(2026, 11, 12))
        self.assertEqual(sorted(n.orgao for n in novos), ["PC-BA", "SEFAZ-MG"])
        self.assertTrue(saude["banca"]["ok"])
        self.assertEqual((saude["banca"]["lidos"], saude["banca"]["relevantes"]), (4, 2))
        self.assertFalse(saude["fora"]["ok"], "fonte fora do ar não derruba as outras e fica registrada")

        with self._get(PAGINA):                      # 2ª leitura: nada novo
            self.assertEqual(vigia.vigiar(date(2026, 11, 12))[0], [])
        self.assertEqual(len(vigia.pendentes()), 2)

        nova = PAGINA.replace("</body>", '<a href="/concursos/tcexx26">Tribunal de Contas do Estado de Goiás</a></body>')
        with self._get(nova):                        # item novo aparece
            novos, _ = vigia.vigiar(date(2026, 11, 12))
        self.assertEqual([n.orgao for n in novos], ["TCE-GO"])

        vigia.tratar([novos[0].id], "irrelevante")
        self.assertEqual(len(vigia.pendentes()), 2)
        with self.assertRaises(ValueError):
            vigia.tratar(["naoexiste"], "irrelevante")

    def test_layout_quebrado_vira_erro(self):
        with self._get("<html><body>manutenção</body></html>"):
            _, saude = vigia.vigiar(date(2026, 11, 12))
        self.assertFalse(saude["banca"]["ok"])
        self.assertIn("nenhum item", saude["banca"]["erro"])


if __name__ == "__main__":
    unittest.main()
