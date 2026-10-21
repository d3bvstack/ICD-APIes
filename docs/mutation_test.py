#!/usr/bin/env python3
"""Mutation test for verify_doc.py.

A conformance checker that cannot fail proves nothing. This harness copies the
docs into a scratch directory, injects one defect at a time, and asserts that
the checker rejects it. A mutation that the checker accepts is a hole in the
test and is reported as such.

Exit code 0 = every mutation was caught, 1 = at least one slipped through.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
CHECKER = SOURCE / "verify_doc.py"
MD = "icd-api-es.md"
HTML = "icd-api-es.html"


def apply_mutation(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError(f"mutation anchor not found: {old!r}")
    if text.count(old) < 1:
        raise AssertionError("anchor vanished")
    return text.replace(old, new, 1)


# (label, file, old, new, expected substring in the failure output)
MUTATIONS: list[tuple[str, str, str, str, str]] = [
    (
        "invented endpoint path",
        MD,
        "`/icd/entity/autocode`",
        "`/icd/entity/autocodev2`",
        "do not exist in the OpenAPI spec",
    ),
    (
        "invented parameter name",
        MD,
        "| `q` | `/icd/entity/search` |",
        "| `qquery` | `/icd/entity/search` |",
        "does not declare",
    ),
    (
        "parameter not valid for that endpoint",
        MD,
        "| `foundationUri` | `/icd/release/11/{releaseId}/{linearizationname}/lookup` |",
        "| `foundationUri` | `/icd/release/11/{releaseId}/{linearizationname}/search` |",
        "does not declare",
    ),
    (
        "Spanish availability wrong for MMS 2020-09",
        MD,
        "| `2020-09` | ✔ | Árabe, Inglés, **Español** | — |",
        "| `2020-09` | ✔ | Árabe, Inglés | — |",
        "MMS Spanish availability is wrong",
    ),
    (
        "Spanish availability wrong for ICF 2024-01",
        MD,
        "| `2024-01` | ✔ | Árabe, Chino, Checo, Inglés, Francés, Portugués, Ruso, **Español**, Turco, Uzbeko | Checo, Inglés, Turco |",
        "| `2024-01` | ✔ | Árabe, Chino, Checo, Inglés, Francés, Portugués, Ruso, **Español**, Turco, Uzbeko | Checo, Inglés, Turco, **Español** |",
        "ICF Spanish availability is wrong",
    ),
    (
        "missing release row in the matrix",
        MD,
        "| `2019-04` | ✔ | Inglés | — |",
        "| `2019-04` | ✔ | Inglés | — |\n| `2017-01` | ✔ | Inglés | — |",
        "does not cover exactly the official releases",
    ),
    (
        "mandatory header undocumented",
        HTML,
        '<code>Accept-Language</code>',
        '<code>Accept-Language-X</code>',
        "mandatory header 'Accept-Language'",
    ),
    (
        "OAuth scope removed",
        MD,
        "scope=icdapi_access",
        "scope=icdapi_read",
        "'icdapi_access' OAuth2 scope",
    ),
    (
        "broken shell sample",
        MD,
        "curl -sS -X POST https://icdaccessmanagement.who.int/connect/token \\\n",
        "curl -sS -X POST https://icdaccessmanagement.who.int/connect/token \\\n  if [ ; then\n",
        "code sample(s) that do not parse",
    ),
    (
        "broken python sample",
        MD,
        '    """Busca un término, autocompleta y verifica el código resultante."""',
        '    """Busca un término, autocompleta y verifica el código resultante."""\n    def broken(:',
        "code sample(s) that do not parse",
    ),
    (
        "th without scope",
        HTML,
        '<th scope="col">Dato</th>',
        '<th>Dato</th>',
        "without a scope attribute",
    ),
    (
        "table without caption",
        HTML,
        "<caption>Datos clave de la ICD API</caption>",
        "",
        "needs a <caption>",
    ),
    (
        "pre not keyboard-scrollable",
        HTML,
        '<pre role="region" tabindex="0" aria-label="Respuesta JSON del endpoint de token">',
        "<pre>",
        "keyboard users cannot scroll them",
    ),
    (
        "html without lang attribute",
        HTML,
        '<html lang="es">',
        "<html>",
        'must carry lang="es"',
    ),
    (
        "two h1 elements",
        HTML,
        "<h2 id=\"resumen-rapido\">Resumen rápido</h2>",
        "<h1>Resumen rápido</h1>",
        "exactly one <h1>",
    ),
    (
        "skipped heading level",
        HTML,
        '<h3 id="codigo-de-idioma">4.1 Código de idioma</h3>',
        '<h5 id="codigo-de-idioma">4.1 Código de idioma</h5>',
        "skipped heading level",
    ),
    (
        "dangling internal anchor",
        HTML,
        'href="#recursos"',
        'href="#no-existe"',
        "pointing to non-existent ids",
    ),
    (
        "low contrast text colour",
        HTML,
        "--c-text: #1a1a1a;",
        "--c-text: #b9b9b9;",
        "minimum 4.5:1",
    ),
    (
        "dark mode removed",
        HTML,
        "@media (prefers-color-scheme: dark) {",
        "@media (prefers-color-scheme: nonsense) {",
        "dark-mode variant",
    ),
    (
        "print stylesheet removed",
        HTML,
        "@media print {",
        "@media speech {",
        "print stylesheet",
    ),
    (
        "focus styling removed",
        HTML,
        ":focus-visible {",
        ":focus-nothing {",
        ":focus-visible styling",
    ),
    (
        "reduced motion handling removed",
        HTML,
        "@media (prefers-reduced-motion: reduce) {",
        "@media (prefers-reduced-motion: no-preference) {",
        "prefers-reduced-motion",
    ),
    (
        "topic removed from the markdown guide",
        MD,
        "## 12. Recursos",
        "## 12. Otra cosa",
        "does not cover the topic 'recursos'",
    ),
    (
        "html missing a whole section",
        HTML,
        '<h2 id="errores">9. Errores y códigos de estado</h2>',
        "<h2>Otra sección</h2>",
        "required section 'errores'",
    ),
]


def run_checker(root: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(root / "verify_doc.py")],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    failures: list[str] = []
    print("=" * 78)
    print("MUTATION TEST: every injected defect must be rejected by verify_doc.py")
    print("=" * 78)

    for label, target, old, new, expected in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "docs"
            shutil.copytree(SOURCE, root)
            path = root / target
            text = path.read_text(encoding="utf-8")
            try:
                mutated = apply_mutation(text, old, new)
            except AssertionError as exc:
                print(f"  ERROR  {label}: {exc}")
                failures.append(f"{label}: {exc}")
                continue
            path.write_text(mutated, encoding="utf-8")

            code, output = run_checker(root)
            caught = code != 0 and expected in output
            status = "PASS" if caught else "HOLE"
            print(f"  {status:5}  {label}")
            if not caught:
                failures.append(
                    f"{label}: checker returned {code}; expected failure containing {expected!r}"
                )
                tail = [ln for ln in output.splitlines() if "FAIL" in ln][:4]
                for line in tail:
                    print(f"          {line}")

    print("-" * 78)
    if failures:
        print(f"MUTATIONS SLIPPED THROUGH: {len(failures)}")
        for f in failures:
            print(f"  {f}")
        print("=" * 78)
        return 1
    print(f"OK: all {len(MUTATIONS)} mutations were caught by the checker.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
