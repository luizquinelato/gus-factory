# Regras de Backend e Banco de Dados

Estas regras são INEGOCIÁVEIS e devem ser aplicadas em todas as interações e geração de código backend.

## 1. Soft Delete
- NUNCA delete registros físicos do banco de dados (ex: `DELETE FROM tabela`).
- SEMPRE use a exclusão lógica atualizando a coluna `active` para `false` (ex: `UPDATE tabela SET active = false`).
- Todas as consultas devem filtrar por `active = true` por padrão.

## 2. Logging Estruturado
- NUNCA use `print()` no código de produção.
- SEMPRE use o módulo `logging` do Python configurado por módulo (ex: `logger = logging.getLogger(__name__)`).
- Utilize os níveis corretos (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).

## 3. Idioma do Banco de Dados
- O schema SQL, nomes de tabelas e colunas devem ser SEMPRE em inglês.
- A variável `DB_LANGUAGE` (ex: `pt_BR.UTF-8`) define apenas o charset, collation e o idioma dos dados inseridos, não a estrutura.

## 3.1. Nomenclatura do Banco de Dados
- O nome do banco, usuário e senha DEVEM seguir o padrão da chave do projeto (`PROJECT_KEY`).
- **PROD**: `DB_NAME={PROJECT_KEY}`, `DB_USER={PROJECT_KEY}`, `DB_PASS={PROJECT_KEY}`
- **DEV**: `DB_NAME={PROJECT_KEY}_dev`, `DB_USER={PROJECT_KEY}`, `DB_PASS={PROJECT_KEY}`
- Exemplo para o projeto `acme`: banco PROD=`acme`, banco DEV=`acme_dev`, usuário=`acme`, senha=`acme`.
- NUNCA use sufixos como `_db`, `_database` ou `_prod` no nome do banco.

## 4. Validação de Dados
- Utilize Pydantic para validação de entrada e saída em todas as rotas do FastAPI.
- Defina schemas claros e tipados para request e response.

## 5. Paginação e Performance
- Rotas que retornam listas DEVEM implementar paginação (ex: `limit`, `offset`).
- Utilize índices no banco de dados para colunas frequentemente consultadas (ex: `tenant_id`, `active`).

## 6. Integrações e IA
- As configurações de modelos de IA e integrações externas devem residir na tabela `integrations`, não no `.env`.
- O sistema deve suportar fallback automático para integrações (ex: se OpenAI falhar, tentar Anthropic).
- Conexões com modelos de IA devem ser diretas, sem uso de AI Gateways intermediários (como WEX).
