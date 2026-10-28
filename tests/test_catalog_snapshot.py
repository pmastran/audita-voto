"""Catalog snapshot must reflect only official source data or explicit failure."""
from __future__ import annotations
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from scripts import build_site

class CatalogSnapshotTests(unittest.TestCase):
    def test_snapshot_records_only_official_catalog(self):
        fixture = {'api_url': build_site.TSE_CATALOG_API, 'archives': [
            {'uf': 'AC', 'turno': 1, 'url': 'https://cdn.tse.jus.br/official.zip'}
        ]}
        with (TemporaryDirectory() as directory,
              patch.object(build_site, 'DST', Path(directory)),
              patch('audita.tse.official_catalog', return_value=fixture)):
            result = build_site.write_catalog_snapshot()
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['catalog']['archives'], fixture['archives'])

    def test_official_api_failure_produces_no_synthetic_data(self):
        with (TemporaryDirectory() as directory,
              patch.object(build_site, 'DST', Path(directory)),
              patch('audita.tse.official_catalog', side_effect=RuntimeError('source unavailable'))):
            result = build_site.write_catalog_snapshot()
            self.assertEqual(result['status'], 'error')
            self.assertNotIn('catalog', result)
            self.assertNotIn('archives', result)

    def test_unknown_source_is_rejected(self):
        with (TemporaryDirectory() as directory,
              patch.object(build_site, 'DST', Path(directory)),
              patch('audita.tse.official_catalog', return_value={
                  'api_url': 'https://example.com/not-official', 'archives': []
              })):
            result = build_site.write_catalog_snapshot()
            self.assertEqual(result['status'], 'error')
            self.assertNotIn('catalog', result)

if __name__ == '__main__':
    unittest.main()
