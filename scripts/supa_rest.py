"""Gravação restrita ao GitHub Actions, nunca executada pelo browser."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def upsert(table: str, rows: list[dict], conflict: str) -> None:
    if table not in {"av_catalogos", "av_relatorios"}:
        raise ValueError("Tabela não permitida")
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("Variáveis SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY são obrigatórias no GitHub Actions.")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".supabase.co"):
        raise RuntimeError("URL Supabase inválida; permitido apenas HTTPS e domínio .supabase.co.")
    endpoint = f"{url}/rest/v1/{table}?on_conflict={urllib.parse.quote(conflict)}"
    data = json.dumps(rows, ensure_ascii=False, allow_nan=False).encode("utf-8")
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    if key.count(".") == 2:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            if res.status not in (200, 201, 204):
                raise RuntimeError(f"Erro ao persistir no Supabase: HTTP {res.status}")
    except urllib.error.HTTPError as e:
        # Não revelar conteúdo de headers nem segredos em mensagens de erro.
        raise RuntimeError(f"Erro de gravação no Supabase HTTP {e.code}. Confira schema, grants e RLS.") from None
