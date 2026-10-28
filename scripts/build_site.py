"""Gera config.js pública, contendo SOMENTE valores públicos (não service role)."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import urllib.parse

ROOT=Path(__file__).resolve().parent.parent
DST=ROOT/'_site'
if DST.exists(): shutil.rmtree(DST)
shutil.copytree(ROOT/'public', DST)
url=os.getenv('AUDITA_SUPABASE_URL','').strip().rstrip('/')
public_key=os.getenv('AUDITA_SUPABASE_PUBLISHABLE_KEY','').strip()
repo=os.getenv('GITHUB_REPOSITORY','').strip()
if url:
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co'):
        raise ValueError('AUDITA_SUPABASE_URL precisa ser HTTPS de um projeto supabase.co')
if public_key and not (public_key.startswith('sb_publishable_') or public_key.count('.')==2):
    raise ValueError('Use somente chave publishable (sb_publishable_*) ou anon legada; nunca a service role')
if public_key.startswith('sb_secret_') or 'service_role' in public_key.lower():
    raise ValueError('Credencial secreta não pode ser exposta no site')
config={'supabaseUrl':url,'supabasePublishableKey':public_key,'githubRepository':repo}
(DST/'config.js').write_text('window.AUDITA_CONFIG = '+json.dumps(config,ensure_ascii=False)+';\n')
print('Build do site estático concluído. Supabase configurado:',bool(url and public_key))
