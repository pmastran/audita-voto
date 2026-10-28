"""Auditoria deterministica de arquivos BWEB oficiais. Nenhuma inferencia de fraude."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

PARSER_VERSION = "auditavoto-bweb-v1.0.0"
MAX_CSV_UNCOMPRESSED = 450 * 1024 * 1024


class SchemaError(ValueError):
    pass


@dataclass
class Section:
    uf: str
    municipality_code: str
    municipality_name: str
    zone: str
    section: str
    turnout: int | None = None
    apt: int | None = None
    abstentions: int | None = None
    votes: dict[str, int] = field(default_factory=dict)
    turnout_values: set[int] = field(default_factory=set)

    def id(self) -> dict[str, Any]:
        return {
            "uf": self.uf,
            "codigo_municipio": self.municipality_code,
            "municipio": self.municipality_name,
            "zona": self.zone,
            "secao": self.section,
            "comparecimento": self.turnout,
            "aptos": self.apt,
            "abstencoes": self.abstentions,
        }


def _safe_int(v: str | None) -> int | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def _label(row: dict[str, str]) -> str:
    return str(row.get("NM_VOTAVEL") or "").strip()


def _is_president(row: dict[str, str]) -> bool:
    code = str(row.get("CD_CARGO_PERGUNTA") or row.get("CD_CARGO") or "").strip()
    name = str(row.get("DS_CARGO_PERGUNTA") or row.get("DS_CARGO") or "").casefold().strip()
    # Se o codigo estiver presente e consistente, valido para o cargo Presidente.
    # Caso contrario, exige descricao literal.
    return code == "1" or "presidente" in name


def parse_official_bweb(path: str, uf: str, turno: int) -> tuple[dict[tuple[str, str, str], Section], dict[str, dict[str, str]], dict[str, Any]]:
    sections: dict[tuple[str, str, str], Section] = {}
    candidate_names: dict[str, dict[str, str]] = {}
    rows_total = rows_valid = rows_invalid = 0
    with zipfile.ZipFile(path) as z:
        csvs = [i for i in z.infolist() if i.filename.lower().endswith(".csv") and not i.is_dir()]
        if not csvs:
            raise SchemaError("ZIP oficial não contém arquivo CSV.")
        info = max(csvs, key=lambda i: i.file_size)
        if info.file_size > MAX_CSV_UNCOMPRESSED:
            raise SchemaError("CSV descompactado excede o limite desta versão.")
        with z.open(info) as raw:
            with io.TextIOWrapper(raw, encoding="cp1252", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";")
                if not reader.fieldnames:
                    raise SchemaError("CSV oficial não tem cabeçalho reconhecível.")
                names = {x.replace("\ufeff", "").strip(): x for x in reader.fieldnames}
                required = {
                    "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "QT_VOTOS", "NR_VOTAVEL", "QT_COMPARECIMENTO"
                }
                if not required.issubset(names):
                    raise SchemaError(
                        "Layout do CSV difere do esperado; colunas ausentes: " + ", ".join(sorted(required - names.keys()))
                    )
                if "DS_CARGO_PERGUNTA" not in names and "CD_CARGO_PERGUNTA" not in names and "DS_CARGO" not in names:
                    raise SchemaError("Coluna do cargo ausente; não é possível identificar votos de presidente.")
                for record in reader:
                    rows_total += 1
                    row = {name: (record.get(rawname) or "") for name, rawname in names.items()}
                    if not _is_president(row):
                        continue
                    current_uf = (row.get("SG_UF") or uf).strip().upper()
                    row_turno = _safe_int(row.get("NR_TURNO"))
                    if current_uf != uf or (row_turno is not None and row_turno != turno):
                        continue
                    votes_count = _safe_int(row.get("QT_VOTOS"))
                    comparecimento = _safe_int(row.get("QT_COMPARECIMENTO"))
                    municipio = row.get("CD_MUNICIPIO", "").strip()
                    zona = row.get("NR_ZONA", "").strip()
                    secao = row.get("NR_SECAO", "").strip()
                    nr_votavel = row.get("NR_VOTAVEL", "").strip()
                    if not all([municipio, zona, secao, nr_votavel]) or votes_count is None or votes_count < 0:
                        rows_invalid += 1
                        continue
                    tipo = row.get("CD_TIPO_VOTAVEL", "").strip()
                    ds_tipo = row.get("DS_TIPO_VOTAVEL", "").strip()
                    if not tipo:
                        # Campo ausente: no modo nominal nao e confiavel separar categorias.
                        raise SchemaError("Coluna CD_TIPO_VOTAVEL ausente; comparação nominal não é segura.")
                    item_key = (municipio, zona, secao)
                    section = sections.get(item_key)
                    if section is None:
                        section = Section(
                            uf=current_uf,
                            municipality_code=municipio,
                            municipality_name=row.get("NM_MUNICIPIO", "").strip(),
                            zone=zona,
                            section=secao,
                            turnout=comparecimento,
                            apt=_safe_int(row.get("QT_APTOS")),
                            abstentions=_safe_int(row.get("QT_ABSTENCOES")),
                        )
                        sections[item_key] = section
                    if comparecimento is not None:
                        section.turnout_values.add(comparecimento)
                        if section.turnout is None:
                            section.turnout = comparecimento
                    key = tipo + ":" + nr_votavel
                    section.votes[key] = section.votes.get(key, 0) + votes_count
                    if key not in candidate_names:
                        candidate_names[key] = {"numero": nr_votavel, "tipo": ds_tipo or tipo, "nome": _label(row)}
                    rows_valid += 1
    if rows_invalid:
        raise SchemaError(f"Foram encontradas {rows_invalid} linhas presidenciais inválidas. A importação foi interrompida para evitar análises parciais.")
    if not sections:
        raise SchemaError("Nenhuma seção de presidente encontrada para a UF e o turno solicitados.")
    return sections, candidate_names, {
        "linhas_csv": rows_total,
        "linhas_presidente_validas": rows_valid,
        "linhas_presidente_invalidas": rows_invalid,
        "arquivo_csv": info.filename,
        "secoes_lidas": len(sections),
    }


def _sorted_breakdown(section: Section, labels: dict[str, dict[str, str]], nominal_only: bool) -> list[dict[str, Any]]:
    out = []
    for key, count in section.votes.items():
        if nominal_only and not key.startswith("1:"):
            continue
        candidate = labels.get(key, {})
        out.append({
            "numero": candidate.get("numero", key.split(":", 1)[-1]),
            "nome": candidate.get("nome") or candidate.get("tipo") or "Votável identificado por número",
            "tipo": candidate.get("tipo", key.split(":")[0]),
            "votos": count,
        })
    return sorted(out, key=lambda x: (-x["votos"], x["numero"]))


def audit_sections(
    sections: dict[tuple[str, str, str], Section],
    labels: dict[str, dict[str, str]],
    *,
    uf: str,
    turno: int,
    mode: str = "completo",
    min_turnout: int = 100,
    min_sections: int = 2,
    same_municipality: bool = True,
    max_groups: int = 100,
) -> dict[str, Any]:
    if mode not in ("completo", "nominal"):
        raise ValueError("Modo inválido.")
    if min_sections < 2 or min_sections > 20 or min_turnout < 0 or min_turnout > 9999:
        raise ValueError("Filtros fora dos limites permitidos.")
    groups: dict[tuple[Any, ...], list[Section]] = defaultdict(list)
    problems: list[dict[str, Any]] = []
    violations = 0
    valid_for_comparison = 0
    skipped_missing_turnout = 0
    for sec in sections.values():
        if len(sec.turnout_values) > 1:
            violations += 1
            if len(problems) < 100:
                problems.append({
                    **sec.id(), "regra": "comparecimento_inconsistente_no_csv",
                    "valores_original": sorted(sec.turnout_values),
                    "explicacao": "Uma seção possui valores diferentes de comparecimento entre linhas do arquivo."
                })
        if sec.turnout is not None and sum(sec.votes.values()) != sec.turnout:
            violations += 1
            if len(problems) < 100:
                problems.append({
                    **sec.id(), "regra": "soma_de_votos_diferente_do_comparecimento",
                    "soma_votos": sum(sec.votes.values()),
                    "explicacao": "Para o cargo de presidente, a soma registrada difere do comparecimento informado na seção."
                })
        if sec.turnout is None:
            skipped_missing_turnout += 1
        if sec.turnout is None or sec.turnout < min_turnout or len(sec.turnout_values) != 1:
            continue
        valid_for_comparison += 1
        vector = tuple(sorted(
            (key, value) for key, value in sec.votes.items() if mode == "completo" or key.startswith("1:")
        ))
        if mode == "completo":
            signature = (sec.municipality_code if same_municipality else "UF", sec.turnout, vector)
        else:
            signature = (sec.municipality_code if same_municipality else "UF", vector)
        groups[signature].append(sec)

    repeated = [members for members in groups.values() if len(members) >= min_sections]
    repeated.sort(key=lambda m: (-len(m), -int(m[0].turnout or 0), m[0].municipality_name, m[0].zone))
    findings = []
    for members in repeated[:max_groups]:
        example = members[0]
        signature = json.dumps([x.id() for x in members], ensure_ascii=False, sort_keys=True)
        fid = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
        findings.append({
            "id": fid,
            "categoria": "coincidencia_numerica_estatistica",
            "quantidade_secoes": len(members),
            "municipio": example.municipality_name if same_municipality else "Municípios distintos na UF",
            "comparecimento": example.turnout if mode == "completo" else None,
            "secoes": [s.id() for s in sorted(members, key=lambda s: (s.municipality_name, s.zone, s.section))],
            "votos": _sorted_breakdown(example, labels, mode == "nominal"),
            "regra": "Resultado nominal idêntico" if mode == "nominal" else "Resultado completo idêntico",
            "observacao": "Coincidência observada nos dados publicados. Não é comprovação de irregularidade."
        })
    return {
        "uf": uf,
        "turno": turno,
        "cargo": "Presidente",
        "filtros": {
            "modo": mode, "comparecimento_minimo": min_turnout,
            "minimo_de_secoes": min_sections, "mesmo_municipio": same_municipality,
        },
        "resumo": {
            "secoes_processadas": len(sections),
            "secoes_elegiveis_para_comparacao": valid_for_comparison,
            "secoes_sem_comparecimento": skipped_missing_turnout,
            "municipios": len(set(s.municipality_code for s in sections.values())),
            "grupos_duplicados": len(repeated),
            "grupos_exibidos": len(findings),
            "diferencas_aritmeticas_ou_de_registro": violations,
            "diferencas_exibidas": len(problems),
        },
        "coincidencias": findings,
        "diferencas": problems,
        "aviso": "Resultados repetidos e diferenças de dados precisam de verificação contextual; não implicam fraude."
    }
