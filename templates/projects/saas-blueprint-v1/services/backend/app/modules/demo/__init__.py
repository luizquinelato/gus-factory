"""
modules/demo/__init__.py
========================
Módulo Demo — exemplo funcional do Modular Monolith + Event Bus + Outbox Pattern.

Este arquivo registra o módulo no ModuleRegistry e garante que os handlers
de eventos sejam inscritos no EventBus antes do app subir.

--------------------------------------------------------------------
Como criar um módulo real (ex: cadastros):
--------------------------------------------------------------------

1. Crie a pasta: app/modules/cadastros/

2. Crie os arquivos:
   ├── __init__.py    ← copia e adapta este arquivo
   ├── router.py      ← endpoints REST do módulo
   ├── schemas.py     ← Pydantic models (request/response)
   ├── service.py     ← lógica de negócio + interface pública
   └── events.py      ← EventBus.subscribe() dos eventos consumidos

3. Neste __init__.py, registre o módulo:
   ModuleRegistry.register(
       name   = "cadastros",
       router = router,
       prefix = "/modules/cadastros",
   )

4. Em main.py, adicione a linha de import:
   import app.modules.cadastros  # noqa

   O ModuleRegistry.include_all(api_router) já está no main.py
   e incluirá o novo router automaticamente.

--------------------------------------------------------------------
Regras de isolamento (obrigatórias)
--------------------------------------------------------------------
  ✅ from app.core.*          import ...
  ✅ from app.dependencies.*  import ...
  ✅ from app.schemas.common  import ...
  ✅ from app.modules.outro.service import OutroService   (contrato público)
  ❌ from app.modules.outro.router  import ...            (NUNCA)
  ❌ from app.modules.outro.schemas import ...            (use schemas/common.py)

Eventos entre módulos → EventBus.emit() ou EventBus.emit_reliable()
Nunca acesse tabelas de outro módulo diretamente.
--------------------------------------------------------------------
"""
from app.modules import ModuleRegistry
from app.modules.demo import events  # noqa — registra handlers no EventBus
from app.modules.demo.router import router

ModuleRegistry.register(
    name   = "demo",
    router = router,
    prefix = "/modules/demo",
)
