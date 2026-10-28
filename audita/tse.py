"""Descoberta e download de arquivos oficiais do TSE (sem fontes alternativas)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

CATALOG_URL = (
    "https://dadosabertos.tse.jus.br/api/3/action/package_show"
    "?id=resultados-2026-boletim-de-urna"
)
DATASET_URL = "https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna"
DATA_HOST = "cdn.tse.jus.br"
ALLOWED_UFS = frozenset(
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO ZZ".split()
)
MAX_ZIP_BYTES = int(os.getenv("AUDITA_MAX_ZIP_MB", "60")) * 1024 * 1024
CACHE_SECONDS = 300
_USER_AGENT = "AuditaVoto/1.0 (auditoria documental de dados oficiais)"
_catalog_cache: dict[str, Any] = {"at": 0.0, "data": None}


class OfficialDataError(Exception):
    """Erro explicitamente verificavel de fonte oficial ou integridade."""


def _official_url(url: str) -> bool:
    parts = urllib.parse.urlparse(url)
    return parts.scheme == "https" and parts.hostname == DATA_HOST and not parts.username


def _urlopen(url: str, timeout: int = 35):
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
    return urllib.request.urlopen(req, timeout=timeout)


def _parse_name(name: str) -> tuple[str, int] | None:
    """Parseia UF/turno apenas a partir de identificadores documentados na fonte."""
    n = name.casefold()
    m = re.match(r"^\s*(AC|AL|AM|AP|BA|CE|DF|ES|GO|MA|MG|MS|MT|PA|PB|PE|PI|PR|RJ|RN|RO|RR|RS|SC|SE|SP|TO|ZZ)\s*-", name, re.I)
    if not m:
        return None
    if "primeiro turno" in n or "1º turno" in n or "1o turno" in n:
        return m.group(1).upper(), 1
    if "segundo turno" in n or "2º turno" in n or "2o turno" in n:
        return m.group(1).upper(), 2
    return None


def _parse_filename(url: str) -> tuple[str, int] | None:
    fn = urllib.parse.urlparse(url).path.split("/")[-1]
    m = re.match(r"bweb_([12])t_([A-Z]{2})_\d+\.zip$", fn, re.I)
    if m and m.group(2).upper() in ALLOWED_UFS:
        return m.group(2).upper(), int(m.group(1))
    return None


def official_catalog(force: bool = False) -> dict[str, Any]:
    if not force and _catalog_cache["data"] is not None and time.time() - _catalog_cache["at"] < CACHE_SECONDS:
        return _catalog_cache["data"]
    try:
        with _urlopen(CATALOG_URL) as reply:
            payload = json.load(reply)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        raise OfficialDataError(f"Não foi possível consultar a API oficial do TSE: {e}") from e
    if payload.get("success") is not True or not isinstance(payload.get("result"), dict):
        raise OfficialDataError("A API do TSE não retornou um catálogo válido.")

    data = payload["result"]
    resources = data.get("resources", [])
    archives: dict[tuple[str, int], dict[str, Any]] = {}
    hashes: dict[tuple[str, int], str] = {}
    for item in resources:
        name = str(item.get("name") or "")
        url = str(item.get("url") or "")
        if not _official_url(url):
            continue
        nr = _parse_name(name)
        parsed = _parse_filename(url)
        # O catalogo CKAN pode publicar nomes com padroes diferentes do arquivo.
        # Aceitar identificacao pelo nome somente para ZIP BWEB oficial, com UF/turno explicitos.
        if not parsed and nr and re.search(r"/bweb[^/]*\\.zip$", urllib.parse.urlparse(url).path, re.I):
            parsed = nr
        if parsed and nr and parsed != nr:
            continue
        if parsed and (nr is None or parsed == nr):
            uf, turno = parsed
            archives[(uf, turno)] = {
                "uf": uf,
                "turno": turno,
                "name": name,
                "url": url,
                "resource_id": str(item.get("id") or ""),
                "last_modified": item.get("last_modified") or item.get("metadata_modified"),
                "bytes_declared": item.get("size"),
            }
        if nr and re.search(r"\.sha(256|512|2)$", urllib.parse.urlparse(url).path, re.I):
            hashes[nr] = url

    for key, item in archives.items():
        url = item["url"]
        hash_url = hashes.get(key)
        if not hash_url:
            # Somente arquivo de hash no MESMO dominio oficial; URL derivada
            # nao e tratada como existente antes de consulta HTTP bem-sucedida.
            hash_url = url + ".sha512"
        item["hash_url"] = hash_url
    result = {
        "dataset_url": DATASET_URL,
        "api_url": CATALOG_URL,
        "metadata_modified": data.get("metadata_modified"),
        "retrieved_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "resources_total": len(resources),
        "archives": sorted(archives.values(), key=lambda r: (r["uf"], r["turno"])),
    }
    _catalog_cache.update(at=time.time(), data=result)
    return result


def choose_archive(catalog: dict[str, Any], uf: str, turno: int) -> dict[str, Any]:
    matching = [r for r in catalog["archives"] if r["uf"] == uf and r["turno"] == turno]
    if len(matching) != 1:
        raise OfficialDataError(
            f"Arquivo de Boletins de Urna {uf}, {turno}º turno, indisponível no catálogo oficial consultado."
        )
    return matching[0]


def download_and_check(resource: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Download limitado; compara SHA-512 ao valor publicado pelo TSE antes de analisar."""
    url = resource["url"]
    hurl = resource["hash_url"]
    if not _official_url(url) or not _official_url(hurl):
        raise OfficialDataError("Um endereço da fonte não pertence ao domínio oficial autorizado.")
    try:
        with _urlopen(hurl) as stream:
            hash_text = stream.read(8192).decode("ascii", errors="replace")
    except (urllib.error.URLError, OSError) as e:
        raise OfficialDataError(f"Não foi possível obter o hash oficial SHA-512: {e}") from e
    match = re.search(r"\b([a-fA-F0-9]{128})\b", hash_text)
    if not match:
        raise OfficialDataError("O arquivo oficial de hash não contém um SHA-512 reconhecível.")
    official_digest = match.group(1).lower()
    temp_name = None
    written = 0
    digest = hashlib.sha512()
    try:
        with _urlopen(url, timeout=90) as reply:
            content_size = reply.headers.get("Content-Length")
            if content_size and int(content_size) > MAX_ZIP_BYTES:
                raise OfficialDataError(
                    f"Arquivo de {int(content_size)/1048576:.0f} MiB excede o limite seguro "
                    f"de {MAX_ZIP_BYTES/1048576:.0f} MiB desta versão."
                )
            with tempfile.NamedTemporaryFile(prefix="auditavoto-", suffix=".zip", delete=False) as output:
                temp_name = output.name
                while chunk := reply.read(1024 * 1024):
                    written += len(chunk)
                    if written > MAX_ZIP_BYTES:
                        raise OfficialDataError("Download interrompido: arquivo excedeu o limite seguro.")
                    digest.update(chunk)
                    output.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        if temp_name and os.path.isfile(temp_name):
            os.unlink(temp_name)
        raise OfficialDataError(f"Falha ao obter arquivo do TSE: {e}") from e
    except Exception:
        if temp_name and os.path.isfile(temp_name):
            os.unlink(temp_name)
        raise
    observed_digest = digest.hexdigest()
    if observed_digest != official_digest:
        os.unlink(temp_name)
        raise OfficialDataError("A integridade SHA-512 não confere. O arquivo não será processado.")
    return temp_name, {
        "hash_algoritmo": "SHA-512",
        "sha512": observed_digest,
        "hash_oficial": official_digest,
        "hash_verificado": True,
        "tamanho_bytes": written,
        "arquivo_url": url,
        "hash_url": hurl,
        "recurso_nome": resource["name"],
        "ultima_modificacao": resource.get("last_modified"),
        "resource_id": resource.get("resource_id"),
    }
