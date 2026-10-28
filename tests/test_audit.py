"""Fixtures sinteticas apenas no ambiente isolado de teste; jamais publicadas no app."""
import csv
import json
import os
import tempfile
import unittest
import zipfile
from audita.analyze import SchemaError, audit_sections, parse_official_bweb
from audita.tse import _official_url, _parse_filename, _parse_name

HEADERS = ["NR_TURNO","SG_UF","CD_MUNICIPIO","NM_MUNICIPIO","NR_ZONA","NR_SECAO","CD_CARGO_PERGUNTA","DS_CARGO_PERGUNTA","CD_TIPO_VOTAVEL","DS_TIPO_VOTAVEL","NR_VOTAVEL","NM_VOTAVEL","QT_VOTOS","QT_COMPARECIMENTO","QT_APTOS","QT_ABSTENCOES"]


def row(sec, candidate, votes, typ="1", turnout=250, mun="1000", zone="10", name="Candidato de teste"):
    return ["1","AC",mun,"MUNICIPIO EXEMPLO",zone,str(sec),"1","Presidente",typ,"Nominal" if typ=="1" else "Branco",str(candidate),name,str(votes),str(turnout),"300","50"]


class TestAuditor(unittest.TestCase):
    def get_file(self, records):
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        with zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_DEFLATED) as z:
            import io
            s = io.StringIO()
            w = csv.writer(s, delimiter=";")
            w.writerow(HEADERS)
            w.writerows(records)
            z.writestr("bweb_test.csv", s.getvalue().encode("cp1252"))
        self.addCleanup(lambda: os.remove(tmp.name))
        return tmp.name

    def test_identical_vote_vectors(self):
        # Duas secoes identicas e uma diferente; dados inteiramente sinteticos DE TESTE.
        data = [row(100, 11, 130),row(100, 22, 120),row(101, 11, 130),row(101, 22, 120),row(102, 11, 140),row(102, 22, 110)]
        sections, names, meta = parse_official_bweb(self.get_file(data), "AC", 1)
        result = audit_sections(sections, names, uf="AC", turno=1, min_turnout=100)
        self.assertEqual(result["resumo"]["secoes_processadas"], 3)
        self.assertEqual(result["resumo"]["grupos_duplicados"], 1)
        self.assertEqual(result["coincidencias"][0]["quantidade_secoes"], 2)
        self.assertEqual(result["resumo"]["diferencas_aritmeticas_ou_de_registro"], 0)

    def test_arithmetic_difference_is_separate(self):
        data = [row(100,11,130),row(100,22,119)]
        sections, names, meta = parse_official_bweb(self.get_file(data), "AC", 1)
        result = audit_sections(sections, names, uf="AC", turno=1)
        self.assertEqual(result["resumo"]["diferencas_aritmeticas_ou_de_registro"], 1)
        self.assertEqual(result["diferencas"][0]["soma_votos"], 249)

    def test_different_municipalities_not_compared_by_default(self):
        data = [row(100,11,100),row(100,22,150),row(101,11,100,mun="2000"),row(101,22,150,mun="2000")]
        sections, names, _ = parse_official_bweb(self.get_file(data), "AC", 1)
        result = audit_sections(sections, names, uf="AC", turno=1, same_municipality=True)
        self.assertEqual(result["resumo"]["grupos_duplicados"], 0)

    def test_official_domain_only(self):
        self.assertTrue(_official_url("https://cdn.tse.jus.br/x.zip"))
        self.assertFalse(_official_url("https://not-cdn.tse.jus.br/x.zip"))
        self.assertFalse(_official_url("http://cdn.tse.jus.br/x.zip"))
        self.assertEqual(_parse_filename("https://cdn.tse.jus.br/x/bweb_1t_AC_051020261403.zip"), ("AC",1))
        self.assertEqual(_parse_name("AC - Boletim de Urna - Primeiro turno - 05.10.2026"), ("AC",1))
        self.assertEqual(_parse_name("AC - Hash SHA2 - Primeiro turno - 05.10.2026"), ("AC",1))

    def test_missing_schema_stops_with_error(self):
        path = tempfile.NamedTemporaryFile(suffix=".zip",delete=False)
        path.close()
        self.addCleanup(lambda: os.remove(path.name))
        with zipfile.ZipFile(path.name,"w") as z:
            z.writestr("bad.csv", "X;Y\n1;2\n")
        with self.assertRaises(SchemaError):
            parse_official_bweb(path.name, "AC", 1)

if __name__ == "__main__":
    unittest.main()
