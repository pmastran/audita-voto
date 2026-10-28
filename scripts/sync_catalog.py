"""Sincroniza somente metadados oficiais verificáveis; sem arquivos/valores inventados."""
from __future__ import annotations
from datetime import datetime, timezone
from audita.tse import official_catalog
from scripts.supa_rest import upsert


def sync():
    catalog = official_catalog(force=True)
    if not catalog.get("api_url", "").startswith("https://dadosabertos.tse.jus.br/"):
        raise RuntimeError("Fonte de metadados não é oficial")
    upsert("av_catalogos", [{
        "chave": "tse2026bu",
        "conteudo": catalog,
        "url_origem": catalog["api_url"],
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }], conflict="chave")
    print(f"Catálogo TSE sincronizado: {len(catalog['archives'])} arquivos oficiais identificados. Relatórios não são gerados nesta etapa.")
    return catalog


if __name__ == "__main__":
    sync()
