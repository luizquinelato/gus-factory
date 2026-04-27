#!/usr/bin/env python3
"""
scripts/check_module_imports.py
================================
Enforcer estático de isolamento do Modular Monolith.

Analisa via AST todos os arquivos Python dentro de `app/modules/` e rejeita
imports cruzados ilegais entre módulos.

Regra (allowlist — mais restritiva)
-------------------------------------
  ÚNICO import cross-módulo permitido:
    from app.modules.X.service import ...   ← contrato público síncrono

  TUDO o mais é proibido, incluindo:
    from app.modules.X          import ...  (atinge __init__.py)
    from app.modules.X.router   import ...
    from app.modules.X.repository import ...
    from app.modules.X.schemas  import ...  (use app/schemas/common.py)
    from app.modules.X.models   import ...
    from app.modules.X.events   import ...
    from app.modules.X.utils    import ...

  Para comunicação entre módulos use:
    - EventBus.emit / emit_reliable      (eventos assíncronos)
    - from app.modules.X.service import  (contrato público síncrono)
    - app/schemas/common.py              (tipos compartilhados)

  Sempre permitido (qualquer módulo pode importar):
    from app.core.*          import ...
    from app.dependencies.*  import ...
    from app.schemas.*       import ...

Uso
---
  # Verificar manualmente:
  python scripts/check_module_imports.py

  # Como pre-commit hook (instale pre-commit e adicione ao .pre-commit-config.yaml):
  #   - repo: local
  #     hooks:
  #       - id: check-module-imports
  #         name: Check cross-module imports
  #         entry: python services/backend/scripts/check_module_imports.py
  #         language: python
  #         pass_filenames: false

Exit codes: 0 = OK, 1 = violações encontradas.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# ── Configuração ──────────────────────────────────────────────────────────────

MODULES_ROOT = Path(__file__).parent.parent / "app" / "modules"

# Único submódulo que pode ser importado de outro módulo (allowlist).
ALLOWED_CROSS_MODULE_SUBMODULE = "service"

# ── Análise ───────────────────────────────────────────────────────────────────


def get_module_name(path: Path) -> str | None:
    """Retorna o nome do módulo de negócio ao qual o arquivo pertence, ou None."""
    try:
        parts = path.relative_to(MODULES_ROOT).parts
        if len(parts) >= 1 and parts[0] != "__pycache__":
            return parts[0]
    except ValueError:
        pass
    return None


def check_file(path: Path, owner_module: str) -> list[str]:
    """Analisa um arquivo e retorna lista de violações encontradas."""
    violations: list[str] = []

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        violations.append(f"{path}: erro de parse — {exc}")
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue

        module_str = ""
        if isinstance(node, ast.ImportFrom) and node.module:
            module_str = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module_str = alias.name

        if not module_str.startswith("app.modules."):
            continue

        # app.modules.<target_module>[.<submodule>]
        parts = module_str.split(".")
        if len(parts) < 3:
            continue

        target_module = parts[2]
        submodule     = parts[3] if len(parts) > 3 else ""

        # Ignorar auto-imports (módulo importando de si mesmo)
        if target_module == owner_module:
            continue

        # Allowlist: somente app.modules.<target>.service é permitido cross-módulo.
        # Qualquer outro caminho (incluindo importar direto do __init__.py,
        # .router, .repository, .schemas, .events, .utils etc.) é violação.
        if submodule != ALLOWED_CROSS_MODULE_SUBMODULE:
            if submodule:
                reason = f"'{submodule}' é privado do módulo '{target_module}' — use '{target_module}.service'"
            else:
                reason = f"importar de '{target_module}' diretamente (via __init__.py) é proibido — use '{target_module}.service'"
            violations.append(
                f"{path}:{node.lineno}: import ilegal — "
                f"'{owner_module}' não pode importar '{module_str}' ({reason})"
            )

    return violations


def main() -> int:
    if not MODULES_ROOT.exists():
        print(f"⚠️  Pasta {MODULES_ROOT} não encontrada. Nenhum módulo para verificar.")
        return 0

    all_violations: list[str] = []

    for py_file in sorted(MODULES_ROOT.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        owner = get_module_name(py_file)
        if not owner:
            continue
        all_violations.extend(check_file(py_file, owner))

    if all_violations:
        print(f"❌ {len(all_violations)} violação(ões) de isolamento encontrada(s):\n")
        for v in all_violations:
            print(f"  {v}")
        print()
        print("Corrija os imports antes de commitar.")
        print("Dica: use EventBus para comunicação entre módulos,")
        print("      ou importe apenas '<modulo>.service' para contratos públicos.")
        return 1

    modules = sorted({get_module_name(p) for p in MODULES_ROOT.rglob("*.py")
                      if get_module_name(p) and "__pycache__" not in p.parts})
    print(f"✅ Módulos verificados: {', '.join(modules) or '(nenhum)'} — sem violações.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
