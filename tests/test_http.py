"""Teste end-to-end em servidor local com arquivo sintetico DE TESTE, sem acesso a TSE."""
import csv
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from unittest.mock import patch

from http.server import ThreadingHTTPServer
from server import AuditHTTPHandler
from tests.test_audit import HEADERS, row


class ServerSmokeTest(unittest.TestCase):
    def test_api_audit_local_fixture(self):
        tmp = tempfile.NamedTemporaryFile(suffix='.zip',delete=False)
        tmp.close()
        with zipfile.ZipFile(tmp.name,'w',zipfile.ZIP_DEFLATED) as z:
            s=io.StringIO(); w=csv.writer(s,delimiter=';'); w.writerow(HEADERS)
            w.writerows([row(100,11,100),row(100,22,150),row(101,11,100),row(101,22,150)])
            z.writestr('test.csv',s.getvalue().encode('cp1252'))
        server=ThreadingHTTPServer(('127.0.0.1',0),AuditHTTPHandler)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.shutdown)
        url=f'http://127.0.0.1:{server.server_port}/api/audit'
        with patch('server.official_catalog', return_value={'archives':[{'uf':'AC','turno':1,'name':'test','url':'https://cdn.tse.jus.br/a.zip','hash_url':'https://cdn.tse.jus.br/a.zip.sha512'}],'dataset_url':'https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna','api_url':'https://dadosabertos.tse.jus.br/api/3/action/package_show?id=x','metadata_modified':None,'retrieved_at':'2026-10-28T17:00:00Z'}),patch('server.download_and_check',side_effect=lambda _: (tmp.name,{'arquivo_url':'https://cdn.tse.jus.br/a.zip','hash_url':'https://cdn.tse.jus.br/a.zip.sha512','hash_verificado':True,'sha512':'test-hash','recurso_nome':'test'})):
            request=urllib.request.Request(url,data=json.dumps({'uf':'AC','turno':1,'modo':'completo','comparecimento_minimo':100,'minimo_secoes':2,'mesmo_municipio':True}).encode(),headers={'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(request) as response:
                data=json.load(response)
        self.assertEqual(data['resumo']['grupos_duplicados'],1)
        self.assertEqual(data['resumo']['secoes_processadas'],2)
        self.assertTrue(data['origem']['hash_verificado'])

if __name__=='__main__': unittest.main()
