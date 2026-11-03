"""Testes do classificador. Os textos abaixo são FICTÍCIOS, escritos no
formato típico dos atos do DOU/diários, só para validar as regras."""

import unittest

from radar.classificador import (
    classificar, extrair_inscricoes, extrair_salario, extrair_vagas, identificar_orgao, normalizar,
)
from radar.modelos import Area, Publicacao, TipoEvento


def pub(titulo, texto, hierarquia="", municipio=None, uf=None, fonte="DOU"):
    return Publicacao(fonte, "2026-11-03", titulo, texto, "https://exemplo/ato", hierarquia, uf, municipio)


class TestTipos(unittest.TestCase):
    def test_autorizacao_mgi(self):
        ev = classificar(pub(
            "PORTARIA MGI Nº 9.999, DE 30 DE OUTUBRO DE 2026",
            "A MINISTRA DE ESTADO DA GESTÃO E DA INOVAÇÃO EM SERVIÇOS PÚBLICOS resolve: Art. 1º Autorizar a "
            "realização de concurso público para o provimento de 500 (quinhentos) cargos de Auditor-Fiscal da "
            "Receita Federal do Brasil, do quadro de pessoal da Secretaria Especial da Receita Federal do Brasil.",
            "Ministério da Gestão e da Inovação em Serviços Públicos/Gabinete da Ministra",
        ))
        self.assertEqual(ev.tipo, TipoEvento.AUTORIZACAO)
        self.assertEqual(ev.orgao.sigla, "RFB")
        self.assertEqual(ev.area, Area.FISCAL)
        self.assertEqual(ev.vagas, 500)
        self.assertIn("Auditor-Fiscal da Receita Federal", ev.cargos)

    def test_comissao(self):
        ev = classificar(pub(
            "PORTARIA Nº 123, DE 1º DE NOVEMBRO DE 2026",
            "O DIRETOR-GERAL DA POLÍCIA RODOVIÁRIA FEDERAL resolve: Art. 1º Instituir a Comissão Organizadora "
            "do concurso público para provimento de cargos de Policial Rodoviário Federal.",
        ))
        self.assertEqual(ev.tipo, TipoEvento.COMISSAO)
        self.assertEqual(ev.orgao.sigla, "PRF")
        self.assertEqual(ev.area, Area.POLICIAL)

    def test_dispensa_banca(self):
        ev = classificar(pub(
            "AVISO DE CONTRATAÇÃO DIRETA",
            "Dispensa de licitação nº 10/2026, com fundamento no art. 75, XV, da Lei nº 14.133/2021. Objeto: "
            "contratação do Centro Brasileiro de Pesquisa em Avaliação e Seleção e de Promoção de Eventos – "
            "Cebraspe para organização e realização de concurso público do Tribunal de Contas da União.",
        ))
        self.assertEqual(ev.tipo, TipoEvento.BANCA_DEFINIDA)
        self.assertEqual(ev.banca, "Cebraspe")
        self.assertEqual(ev.orgao.sigla, "TCU")

    def test_extrato_contrato(self):
        ev = classificar(pub(
            "EXTRATO DE CONTRATO Nº 5/2026",
            "Contratante: Secretaria de Estado da Fazenda de Minas Gerais. Contratada: Fundação Getulio Vargas. "
            "Objeto: prestação de serviços para planejamento, organização e realização de concurso público para "
            "o cargo de Auditor Fiscal da Receita Estadual. Valor: R$ 3.000.000,00.",
            fonte="DOE",
        ))
        self.assertEqual(ev.tipo, TipoEvento.CONTRATO_BANCA)
        self.assertEqual(ev.orgao.sigla, "SEFAZ-MG")
        self.assertEqual(ev.orgao.uf, "MG")
        self.assertEqual(ev.banca, "FGV")
        self.assertIsNone(ev.salario_max)  # valor do contrato não é salário

    def test_edital_abertura(self):
        ev = classificar(pub(
            "EDITAL Nº 1 – PC-SP, DE 3 DE NOVEMBRO DE 2026",
            "A Polícia Civil do Estado de São Paulo torna pública a realização de concurso público para o cargo "
            "de Delegado de Polícia, com total de 300 vagas, sob responsabilidade da Fundação Vunesp. "
            "As inscrições estarão abertas no período de 10/11/2026 a 10/12/2026. A remuneração inicial é de "
            "R$ 14.700,00. A homologação do resultado final será publicada no Diário Oficial.",
        ))
        self.assertEqual(ev.tipo, TipoEvento.EDITAL_ABERTURA)
        self.assertEqual(ev.orgao.sigla, "PC-SP")
        self.assertEqual(ev.banca, "Vunesp")
        self.assertEqual(ev.vagas, 300)
        self.assertEqual(ev.salario_max, 14700.0)
        self.assertEqual((ev.inscricoes_inicio, ev.inscricoes_fim), ("2026-11-10", "2026-12-10"))

    def test_homologacao(self):
        ev = classificar(pub(
            "EDITAL Nº 20 – CGU, DE 3 DE NOVEMBRO DE 2026",
            "Torna pública a homologação do resultado final do concurso público para o cargo de Auditor Federal "
            "de Finanças e Controle da Controladoria-Geral da União.",
        ))
        self.assertEqual(ev.tipo, TipoEvento.HOMOLOGACAO)
        self.assertEqual(ev.orgao.sigla, "CGU")

    def test_retificacao(self):
        ev = classificar(pub(
            "EDITAL Nº 2 – PF, DE 3 DE NOVEMBRO DE 2026 – RETIFICAÇÃO",
            "Torna pública a retificação do edital de abertura do concurso público da Polícia Federal.",
        ))
        self.assertEqual(ev.tipo, TipoEvento.RETIFICACAO)
        self.assertEqual(ev.orgao.sigla, "PF")


class TestFiltros(unittest.TestCase):
    def test_ignora_area_fora_do_escopo(self):
        self.assertIsNone(classificar(pub(
            "EDITAL Nº 1", "A Universidade Federal X torna pública a realização de concurso público para "
            "professor do magistério superior.")))

    def test_ignora_nao_concurso(self):
        self.assertIsNone(classificar(pub(
            "PORTARIA Nº 4", "Designa servidor da Receita Federal para função comissionada.")))

    def test_municipal_por_cargo(self):
        ev = classificar(pub(
            "Diário Oficial de Campinas/SP",
            "Fica autorizada a realização de concurso público para o cargo de Auditor Fiscal Tributário "
            "Municipal.", municipio="Campinas", uf="SP", fonte="Querido Diário"))
        self.assertEqual(ev.tipo, TipoEvento.AUTORIZACAO)
        self.assertEqual(ev.area, Area.FISCAL)
        self.assertEqual(ev.orgao.esfera, "municipal")
        self.assertEqual(ev.orgao.nome, "Prefeitura de Campinas/SP")

    def test_filtra_por_area(self):
        texto = "Fica autorizada a realização de concurso público da Polícia Federal."
        self.assertIsNone(classificar(pub("PORTARIA", texto), {Area.FISCAL}))
        self.assertIsNotNone(classificar(pub("PORTARIA", texto), {Area.POLICIAL}))


class TestExtracao(unittest.TestCase):
    def test_orgaos(self):
        casos = {
            "tribunal de contas do estado do rio grande do sul": "TCE-RS",
            "tribunal de contas dos municipios do estado de goias": "TCM-GO",
            "secretaria de estado de economia do distrito federal": "SEFAZ-DF",
            "secretaria da fazenda do estado de sao paulo": "SEFAZ-SP",
            "policia militar do parana": "PM-PR",
            "concurso sefaz-ce 2026": "SEFAZ-CE",
            "policia penal federal": "PPF",
        }
        for texto, sigla in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(identificar_orgao(texto).sigla, sigla)

    def test_inscricoes_por_extenso(self):
        t = normalizar("As inscrições ficarão abertas de 5 a 25 de janeiro de 2027.")
        self.assertEqual(extrair_inscricoes(t), ("2027-01-05", "2027-01-25"))

    def test_inscricoes_ate(self):
        t = normalizar("Período de inscrições: das 10h do dia 1º/12/2026 até as 18h do dia 20/12/2026.")
        self.assertEqual(extrair_inscricoes(t), ("2026-12-01", "2026-12-20"))

    def test_salario_ignora_taxa(self):
        t = normalizar("Taxa de inscrição: R$ 150,00. Remuneração: subsídio de R$ 22.921,71.")
        self.assertEqual(extrair_salario(t), 22921.71)

    def test_vagas(self):
        self.assertEqual(extrair_vagas(normalizar("serão oferecidas 1.000 (mil) vagas")), 1000)


if __name__ == "__main__":
    unittest.main()
