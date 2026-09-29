"""Genera patches BKL-002C desde un USER_SOURCE exportado en Markdown.

Uso:
    python generate_patches.py USER_SOURCE_yyyymmddhhmm.txt

El script falla si los procedures reales no coinciden con los hashes revisados.
No se conecta a Oracle y solo escribe dentro de su propio directorio.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys


EXPECTED = {
    "PRC_APLICAR_REGLAS_ALERTA": {
        "lines": 191,
        "sha256": "a7c98788a7b0d80103466b1a631dd0e0ce55f98c1b34556acabf5056e58c6b50",
    },
    "PRC_UPD_ALERTAS_VAL": {
        "lines": 772,
        "sha256": "e770b0d949573a8aca29aabb00bd89d418c432f6a6b3903fb934d98e2568505a",
    },
}


def parse_user_source(path: Path) -> dict[str, list[str]]:
    procedures: dict[str, list[tuple[int, str]]] = {}
    pattern = re.compile(r"^\|([^|]*)\|([^|]*)\|([^|]*)\|(.*)\|$")

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(raw_line)
        if not match:
            continue
        name, object_type, line_number, text = (
            value.strip() for value in match.groups()
        )
        if object_type != "PROCEDURE" or not line_number.isdigit():
            continue
        if text.endswith("¶"):
            text = text[:-1]
        procedures.setdefault(name, []).append((int(line_number), text))

    result: dict[str, list[str]] = {}
    for name, rows in procedures.items():
        rows.sort(key=lambda item: item[0])
        expected_numbers = list(range(1, len(rows) + 1))
        actual_numbers = [number for number, _text in rows]
        if actual_numbers != expected_numbers:
            raise RuntimeError(f"Fuente discontinuo para {name}: {actual_numbers}")
        result[name] = [text for _number, text in rows]
    return result


def digest(lines: list[str]) -> str:
    body = "\n".join(lines) + "\n"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def validate(procedures: dict[str, list[str]]) -> None:
    for name, expected in EXPECTED.items():
        lines = procedures.get(name)
        if lines is None:
            raise RuntimeError(f"Falta {name} en USER_SOURCE.")
        actual_hash = digest(lines)
        if len(lines) != expected["lines"] or actual_hash != expected["sha256"]:
            raise RuntimeError(
                f"Baseline inesperado para {name}: lines={len(lines)} "
                f"sha256={actual_hash}"
            )


def create_ddl(lines: list[str]) -> list[str]:
    ddl = list(lines)
    ddl[0] = "CREATE OR REPLACE " + ddl[0]
    return ddl


def patch_lease(name: str, source: list[str]) -> list[str]:
    lines = create_ddl(source)
    as_index = next(i for i, line in enumerate(lines) if line.strip() == "AS")
    lines.insert(as_index + 1, "    v_bkl002c_lease_adquirido BOOLEAN := FALSE;")

    begin_index = next(
        i for i in range(as_index + 1, len(lines)) if lines[i].strip() == "BEGIN"
    )
    acquire = [
        "    USR_LAB.PKG_ALERTA_LEASE.ADQUIRIR;",
        "    v_bkl002c_lease_adquirido := TRUE;",
    ]
    lines[begin_index + 1:begin_index + 1] = acquire

    commit_indexes = [
        i for i, line in enumerate(lines) if line.strip().upper() == "COMMIT;"
    ]
    if len(commit_indexes) != 1:
        raise RuntimeError(f"{name} debe contener un COMMIT, encontro {len(commit_indexes)}")
    commit_index = commit_indexes[0]
    success_release = [
        "",
        "    USR_LAB.PKG_ALERTA_LEASE.LIBERAR;",
        "    v_bkl002c_lease_adquirido := FALSE;",
    ]
    lines[commit_index + 1:commit_index + 1] = success_release

    exception_index = max(
        i for i, line in enumerate(lines) if line.strip().upper() == "EXCEPTION"
    )
    rollback_index = next(
        i
        for i in range(exception_index + 1, len(lines))
        if lines[i].strip().upper() == "ROLLBACK;"
    )
    failure_release = [
        "        IF v_bkl002c_lease_adquirido THEN",
        "            BEGIN",
        "                USR_LAB.PKG_ALERTA_LEASE.LIBERAR;",
        "                v_bkl002c_lease_adquirido := FALSE;",
        "            EXCEPTION",
        "                WHEN OTHERS THEN",
        "                    DBMS_OUTPUT.PUT_LINE(",
        "                        'Error liberando lease BKL-002C: ' || SQLERRM",
        "                    );",
        "            END;",
        "        END IF;",
    ]
    lines[rollback_index + 1:rollback_index + 1] = failure_release

    header = [
        f"-- Generado mecanicamente desde USER_SOURCE_202609241052.txt: {name}.",
        f"-- Baseline SHA-256: {EXPECTED[name]['sha256']}",
        "-- Unicos cambios: adquirir/liberar PKG_ALERTA_LEASE y estado local booleano.",
        "",
        "WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK",
        "",
    ]
    return header + lines + ["/", "", f"SHOW ERRORS PROCEDURE USR_LAB.{name}", ""]


def rollback_script(procedures: dict[str, list[str]]) -> list[str]:
    lines = [
        "-- BKL-002C - rollback conservador.",
        "-- Deshabilita jobs nuevos y restaura literalmente los dos procedures baseline.",
        "-- No elimina tablas, solicitudes ni auditoria.",
        "",
        "WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK",
        "",
        "BEGIN",
        "    FOR r IN (",
        "        SELECT JOB_NAME",
        "        FROM USER_SCHEDULER_JOBS",
        "        WHERE JOB_NAME IN (",
        "            'JOB_PROCESAR_RECALC_ALERTAS',",
        "            'JOB_LIMPIAR_HIST_UBICACION'",
        "        )",
        "          AND ENABLED = 'TRUE'",
        "    ) LOOP",
        "        DBMS_SCHEDULER.DISABLE('USR_LAB.' || r.JOB_NAME);",
        "    END LOOP;",
        "END;",
        "/",
        "",
    ]
    for name in ("PRC_UPD_ALERTAS_VAL", "PRC_APLICAR_REGLAS_ALERTA"):
        lines.extend(
            [
                f"-- Restore {name}; SHA-256 fuente: {EXPECTED[name]['sha256']}",
                *create_ddl(procedures[name]),
                "/",
                "",
                f"SHOW ERRORS PROCEDURE USR_LAB.{name}",
                "",
            ]
        )
    return lines


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python generate_patches.py USER_SOURCE.txt")
    source_path = Path(sys.argv[1]).resolve()
    procedures = parse_user_source(source_path)
    validate(procedures)
    output_dir = Path(__file__).resolve().parent

    write_lines(
        output_dir / "05_patch_prc_upd_alertas_val.sql",
        patch_lease("PRC_UPD_ALERTAS_VAL", procedures["PRC_UPD_ALERTAS_VAL"]),
    )
    write_lines(
        output_dir / "06_patch_prc_aplicar_reglas_alerta.sql",
        patch_lease(
            "PRC_APLICAR_REGLAS_ALERTA",
            procedures["PRC_APLICAR_REGLAS_ALERTA"],
        ),
    )
    write_lines(output_dir / "10_rollback.sql", rollback_script(procedures))

    manifest = [
        f"source_file={source_path.name}",
        "generated_by=generate_patches.py",
    ]
    for name in sorted(EXPECTED):
        manifest.append(
            f"{name}:lines={len(procedures[name])}:sha256={digest(procedures[name])}"
        )
    write_lines(output_dir / "source_manifest.txt", manifest + [""])


if __name__ == "__main__":
    main()
