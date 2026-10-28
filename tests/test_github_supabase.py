"""Testes isolados, SEM dados publicados; nunca usam fontes de votos fictícias no site."""
from __future__ import annotations
import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.run_audit import report_key, audit
from scripts.supa_rest import upsert


class GithubSupabaseTests(unittest.TestCase):
    @staticmethod
    def opts():
        return argparse.Namespace(uf="AC",turno=1,modo="completo",comparecimento_minimo=100,minimo_secoes=2,mesmo_municipio=True)

    def test_idempotent_report_key(self):
        options=self.opts()
        sha="a"*128
        self.assertEqual(report_key(options,sha),report_key(options,sha))
        self.assertNotEqual(report_key(options,sha),report_key(options,"b"*128))
        options.modo="nominal"
        self.assertNotEqual(report_key(options,sha),report_key(self.opts(),sha))

    def test_invalid_uf_blocks_before_downloading(self):
        options=self.opts()
        options.uf="invalid"
        with patch("scripts.run_audit.sync") as mocked:
            with self.assertRaises(ValueError):
                audit(options)
            mocked.assert_not_called()

    def test_invalid_sha_prevents_publishing(self):
        with tempfile.NamedTemporaryFile(suffix='.zip',delete=False) as temp:
            file_path=temp.name
        try:
            with patch("scripts.run_audit.sync",return_value={"archives":[{}]}), \
                 patch("scripts.run_audit.choose_archive",return_value={"url":"https://cdn.tse.jus.br/test.zip"}), \
                 patch("scripts.run_audit.download_and_check",return_value=(file_path,{"hash_verificado":False})), \
                 patch("scripts.run_audit.upsert") as writer:
                with self.assertRaises(RuntimeError):
                    audit(self.opts())
                writer.assert_not_called()
        finally:
            if os.path.exists(file_path): os.unlink(file_path)

    def test_supabase_write_needs_secret(self):
        with patch.dict(os.environ,{"SUPABASE_URL":"","SUPABASE_SERVICE_ROLE_KEY":""}):
            with self.assertRaises(RuntimeError):
                upsert("av_catalogos",[{"chave":"tse2026bu"}],"chave")

    def test_github_pages_paths_are_relative(self):
        html=(Path(__file__).parent.parent/'public/index.html').read_text()
        self.assertIn('href="./styles.css"',html)
        self.assertIn('src="./app.js"',html)
        self.assertIn('src="./config.js"',html)
        self.assertNotIn('src="/app.js"',html)

    def test_build_site_cannot_embed_secret(self):
        src=(Path(__file__).parent.parent/'scripts/build_site.py').read_text()
        self.assertNotIn('AUDITA_SUPABASE_SERVICE_ROLE_KEY',src)
        self.assertIn('AUDITA_SUPABASE_PUBLISHABLE_KEY',src)

if __name__=='__main__': unittest.main()
