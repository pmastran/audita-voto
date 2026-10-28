"""Create a static site with public configuration and a real TSE catalog snapshot."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / '_site'
TSE_CATALOG_API = ('https://dadosabertos.tse.jus.br/api/3/action/package_show'
                   '?id=resultados-2026-boletim-de-urna')


def write_catalog_snapshot():
    """Never replace unavailable official records with invented examples."""
    sys.path.insert(0, str(ROOT))
    from audita.tse import official_catalog

    at = datetime.now(timezone.utc).isoformat()
    try:
        catalog = official_catalog(force=True)
        if catalog.get('api_url') != TSE_CATALOG_API or not isinstance(catalog.get('archives'), list):
            raise ValueError('Resposta do catalogo TSE sem proveniencia valida')
        snapshot = {'status': 'ok', 'source': TSE_CATALOG_API,
                    'retrieved_at': at, 'catalog': catalog}
    except Exception as exc:
        snapshot = {'status': 'error', 'source': TSE_CATALOG_API,
                    'retrieved_at': at, 'error': str(exc)}
    target = DST / 'data' / 'catalogo-tse.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Catalog snapshot status:', snapshot['status'])
    if snapshot['status'] == 'ok':
        counts = {str(t): sum(1 for a in snapshot['catalog']['archives'] if a.get('turno') == t) for t in (1, 2)}
        print('TSE catalog diagnosis:', json.dumps({'resources_total': snapshot['catalog']['resources_total'],
            'metadata_modified': snapshot['catalog']['metadata_modified'],
            'archives_by_turn': counts}, ensure_ascii=False))
    else:
        print('TSE catalog error:', snapshot.get('error'))
    return snapshot


def main():
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(ROOT / 'public', DST)
    url = os.getenv('AUDITA_SUPABASE_URL', '').strip().rstrip('/')
    public_key = os.getenv('AUDITA_SUPABASE_PUBLISHABLE_KEY', '').strip()
    repo = os.getenv('GITHUB_REPOSITORY', '').strip()
    if url:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co'):
            raise ValueError('AUDITA_SUPABASE_URL precisa ser HTTPS de um projeto supabase.co')
    if public_key and not (public_key.startswith('sb_publishable_') or public_key.count('.') == 2):
        raise ValueError('Use somente chave publishable (sb_publishable_*) ou anon legada')
    if public_key.startswith('sb_secret_') or 'service_role' in public_key.lower():
        raise ValueError('Credencial secreta nao pode ser exposta no site')
    config = {'supabaseUrl': url, 'supabasePublishableKey': public_key,
              'githubRepository': repo}
    (DST / 'config.js').write_text('window.AUDITA_CONFIG = ' + json.dumps(config, ensure_ascii=False) + ';\n', encoding='utf-8')
    snapshot = write_catalog_snapshot()
    print('Site estatico gerado. Supabase configurado:', bool(url and public_key),
          '| catalogo TSE:', snapshot['status'])
    return snapshot


if __name__ == '__main__':
    main()
