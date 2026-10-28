"""Audita Voto - servidor HTTP sem dependencias externas, pronto para Cloud Run."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from audita.analyze import PARSER_VERSION, SchemaError, audit_sections, parse_official_bweb
from audita.tse import ALLOWED_UFS, OfficialDataError, choose_archive, download_and_check, official_catalog

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
AUDIT_LOCK = threading.Lock()
REPORT_CACHE: dict[str, tuple[float, dict]] = {}
AUDIT_CACHE_SECONDS = 10 * 60
AUDIT_KEY = os.environ.get("AUDITA_RUN_KEY", "").strip()


class AuditHTTPHandler(SimpleHTTPRequestHandler):
    server_version = "AuditaVoto/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()

    def do_GET(self):
        route = urlparse(self.path)
        if route.path == "/api/health":
            self._json(200, {
                "status": "online",
                "app": "Audita Voto",
                "version": "1.0.0",
                "audit_requires_key": bool(AUDIT_KEY),
                "dados_publicados": False,
                "dados_importados": False,
                "observacao": "Auditorias sao executadas sob demanda; nenhuma estatistica e presumida."
            })
            return
        if route.path == "/api/catalog":
            try:
                force = parse_qs(route.query).get("refresh", [""])[0] == "1"
                self._json(200, official_catalog(force=force))
            except OfficialDataError as e:
                self._json(502, {"error": str(e), "source": "TSE"})
            return
        if route.path == "/":
            self.path = "/index.html"
        elif route.path.startswith("/api/"):
            self._json(404, {"error": "Rota de API nao encontrada."})
            return
        super().do_GET()

    def do_POST(self):
        route = urlparse(self.path)
        if route.path != "/api/audit":
            self._json(404, {"error": "Rota de API nao encontrada."})
            return
        if AUDIT_KEY and self.headers.get("X-Audita-Key") != AUDIT_KEY:
            self._json(403, {"error": "Chave de operador invalida ou ausente."})
            return
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            length = 0
        if length <= 0 or length > 4096:
            self._json(413, {"error": "Corpo da solicitacao invalido ou muito grande."})
            return
        try:
            args = json.loads(self.rfile.read(length).decode("utf-8"))
            uf = str(args.get("uf", "")).upper()
            turno = int(args.get("turno", 0))
            mode = str(args.get("modo", "completo"))
            minimum = int(args.get("comparecimento_minimo", 100))
            count = int(args.get("minimo_secoes", 2))
            only_city = args.get("mesmo_municipio", True)
            if not isinstance(only_city, bool):
                raise ValueError("Filtro municipio deve ser booleano.")
            if uf not in ALLOWED_UFS or turno not in (1, 2) or mode not in ("completo", "nominal"):
                raise ValueError("UF, turno ou modo invalido.")
            if not 0 <= minimum <= 9999 or not 2 <= count <= 20:
                raise ValueError("Filtros numericos fora do limite.")
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self._json(400, {"error": f"Parâmetros inválidos: {e}"})
            return
        cache_key = json.dumps([uf, turno, mode, minimum, count, only_city])
        cached = REPORT_CACHE.get(cache_key)
        if cached and time.time() - cached[0] < AUDIT_CACHE_SECONDS:
            self._json(200, {**cached[1], "resposta_em_cache": True})
            return
        if not AUDIT_LOCK.acquire(blocking=False):
            self._json(409, {"error": "Outra auditoria esta em execucao. Tente novamente apos sua conclusao."})
            return
        zip_file = None
        try:
            catalog = official_catalog()
            resource = choose_archive(catalog, uf, turno)
            zip_file, evidence = download_and_check(resource)
            sections, names, parse_info = parse_official_bweb(zip_file, uf, turno)
            result = audit_sections(
                sections, names, uf=uf, turno=turno, mode=mode,
                min_turnout=minimum, min_sections=count,
                same_municipality=only_city, max_groups=150,
            )
            result["origem"] = {
                **evidence,
                "conjunto": catalog["dataset_url"],
                "api_metadados": catalog["api_url"],
                "metadados_atualizados_em": catalog.get("metadata_modified"),
                "catalogo_consultado_em": catalog.get("retrieved_at"),
            }
            result["leitura"] = parse_info
            result["versao_parser"] = PARSER_VERSION
            result["executado_em_utc"] = datetime.now(timezone.utc).isoformat()
            REPORT_CACHE[cache_key] = (time.time(), result)
            self._json(200, result)
        except OfficialDataError as e:
            self._json(422, {"error": str(e), "fonte": "TSE"})
        except (SchemaError, ValueError, OSError) as e:
            self._json(422, {"error": f"Auditoria interrompida por incompatibilidade verificável: {e}"})
        except Exception as e:
            print("Auditoria falhou:", type(e).__name__, str(e), flush=True)
            self._json(500, {"error": "Falha tecnica durante a auditoria. Nenhum resultado foi publicado."})
        finally:
            if zip_file:
                try:
                    os.unlink(zip_file)
                except OSError:
                    pass
            AUDIT_LOCK.release()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AuditHTTPHandler)
    print(f"Audita Voto ouvindo na porta {port}", flush=True)
    server.serve_forever()
