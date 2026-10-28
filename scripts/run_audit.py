"""Audit worker do GitHub Actions. Nunca utiliza fontes de votos não oficiais."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from audita.analyze import PARSER_VERSION, parse_official_bweb, audit_sections
from audita.tse import ALLOWED_UFS, choose_archive, download_and_check
from scripts.sync_catalog import sync
from scripts.supa_rest import upsert


def report_key(args: argparse.Namespace, digest: str) -> str:
    canonical = json.dumps({
        "uf": args.uf, "turno": args.turno, "modo": args.modo,
        "comparecimento_minimo": args.comparecimento_minimo,
        "minimo_secoes": args.minimo_secoes,
        "mesmo_municipio": args.mesmo_municipio,
        "sha512": digest, "parser": PARSER_VERSION,
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def audit(args: argparse.Namespace):
    args.uf = args.uf.upper()
    if args.uf not in ALLOWED_UFS or args.turno not in (1,2):
        raise ValueError("UF ou turno inválido")
    if args.modo not in ("completo", "nominal") or not 0 <= args.comparecimento_minimo <= 9999 or not 2 <= args.minimo_secoes <= 20:
        raise ValueError("Parâmetros fora do intervalo permitido")
    if os.getenv("AUDITA_STATIC_PUBLISH") == "1":
        from audita.tse import official_catalog
        catalog = official_catalog(force=True)
    else:
        catalog = sync()
    source = choose_archive(catalog, args.uf, args.turno)
    path = None
    try:
        path, evidence = download_and_check(source)
        if not evidence.get("hash_verificado") or evidence.get("sha512") != evidence.get("hash_oficial"):
            raise RuntimeError("Relatório bloqueado: hash oficial não confirmado")
        sections, names, parse_info = parse_official_bweb(path, args.uf, args.turno)
        report = audit_sections(sections,names,uf=args.uf,turno=args.turno,mode=args.modo,
            min_turnout=args.comparecimento_minimo,min_sections=args.minimo_secoes,
            same_municipality=args.mesmo_municipio,max_groups=150)
        report["origem"] = {
            **evidence,
            "conjunto": catalog["dataset_url"],
            "api_metadados": catalog["api_url"],
            "metadados_atualizados_em": catalog.get("metadata_modified"),
            "catalogo_consultado_em": catalog.get("retrieved_at"),
        }
        report["leitura"] = parse_info
        report["versao_parser"] = PARSER_VERSION
        report["executado_em_utc"] = datetime.now(timezone.utc).isoformat()
        key = report_key(args, evidence["sha512"])
        if os.getenv("AUDITA_STATIC_PUBLISH") == "1":
            from pathlib import Path
            folder = Path("public/data/reports")
            folder.mkdir(parents=True, exist_ok=True)
            filename = f"{args.uf}-{args.turno}-{args.modo}-{args.comparecimento_minimo}-{args.minimo_secoes}-{str(args.mesmo_municipio).lower()}.json"
            (folder / filename).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            upsert("av_relatorios", [{
            "chave_relatorio": key,
            "uf": args.uf, "turno": args.turno, "modo": args.modo,
            "comparecimento_minimo": args.comparecimento_minimo,
            "minimo_secoes": args.minimo_secoes,
            "mesmo_municipio": args.mesmo_municipio,
            "sha512_oficial": evidence["sha512"],
            "arquivo_url": evidence["arquivo_url"],
            "versao_parser": PARSER_VERSION,
            "executado_em": report["executado_em_utc"],
            "relatorio": report,
            "publicado": True,
            }], conflict="chave_relatorio")
        print("Auditoria salva a partir de fonte oficial. Filtros:",args.uf,args.turno,args.modo,
            "| seções processadas:",report["resumo"]["secoes_processadas"],
            "| grupos repetidos:",report["resumo"]["grupos_duplicados"],
            "| diferenças aritméticas:",report["resumo"]["diferencas_aritmeticas_ou_de_registro"])
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def main():
    parser=argparse.ArgumentParser(description="Audita votos oficiais do TSE por UF/turno")
    parser.add_argument("--uf",required=True)
    parser.add_argument("--turno", type=int,required=True)
    parser.add_argument("--modo",choices=("completo","nominal"),default="completo")
    parser.add_argument("--comparecimento-minimo",type=int,default=100)
    parser.add_argument("--minimo-secoes",type=int,default=2)
    parser.add_argument("--mesmo-municipio",choices=("true","false"),default="true")
    a=parser.parse_args()
    a.mesmo_municipio = (a.mesmo_municipio == "true")
    audit(a)

if __name__ == "__main__": main()
