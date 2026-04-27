"""
app/modules/__init__.py
=======================
Module Registry — infraestrutura central do Modular Monolith.

Como funciona
-------------
Cada módulo de negócio (ex: cadastros, vendas, estoque) registra-se aqui
no seu próprio __init__.py:

    # app/modules/cadastros/__init__.py
    from app.modules import ModuleRegistry
    from app.modules.cadastros import events   # noqa — registra handlers no EventBus
    from app.modules.cadastros.router import router

    ModuleRegistry.register(
        name   = "cadastros",
        router = router,
        prefix = "/modules/cadastros",
    )

O main.py importa cada módulo (triggering o registro) e depois chama
ModuleRegistry.include_all(api_router) — uma única linha.

Regras de isolamento
--------------------
  ✅ módulo → core/*, dependencies/*, schemas/common.py
  ✅ módulo → outro_módulo/service.py  (contrato público de leitura)
  ❌ módulo → outro_módulo/router.py   (nunca)
  ❌ módulo → outro_módulo/repository.py ou schemas.py (nunca)

Eventos entre módulos: usar EventBus.emit() ou EventBus.emit_reliable().
Nunca acessar tabela de outro módulo diretamente.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fastapi import APIRouter

logger = logging.getLogger(__name__)


@dataclass
class _RegisteredModule:
    name:   str
    router: APIRouter
    prefix: str


class ModuleRegistry:
    """
    Singleton de registro de módulos de negócio.

    Uso em main.py:
        # 1. Importe cada módulo para disparar o registro
        import app.modules.demo   # noqa

        # 2. Inclua todos os routers no api_router (antes de app.include_router)
        from app.modules import ModuleRegistry
        ModuleRegistry.include_all(api_router)
    """

    _modules: list[_RegisteredModule] = field(default_factory=list)  # type: ignore[assignment]
    _modules = []  # class-level list (singleton)

    @classmethod
    def register(cls, name: str, router: APIRouter, prefix: str = "") -> None:
        """Registra um módulo. Chamado no __init__.py de cada módulo."""
        if any(m.name == name for m in cls._modules):
            logger.warning("ModuleRegistry: módulo '%s' já registrado — ignorando duplicata.", name)
            return
        cls._modules.append(_RegisteredModule(name=name, router=router, prefix=prefix))
        logger.info("ModuleRegistry: '%s' registrado (prefix='%s').", name, prefix)

    @classmethod
    def include_all(cls, api_router: APIRouter) -> None:
        """Inclui os routers de todos os módulos registrados no api_router do core."""
        for mod in cls._modules:
            api_router.include_router(mod.router, prefix=mod.prefix, tags=[mod.name])
            logger.debug("ModuleRegistry: router '%s' incluído em '%s'.", mod.name, mod.prefix)
        logger.info("ModuleRegistry: %d módulo(s) incluído(s).", len(cls._modules))

    @classmethod
    def names(cls) -> list[str]:
        """Retorna os nomes de todos os módulos registrados."""
        return [m.name for m in cls._modules]

    @classmethod
    def clear(cls) -> None:
        """Remove todos os registros. Útil em testes."""
        cls._modules.clear()
