# Variáveis do Projeto (Template)

Preencha todos os campos abaixo e salve uma cópia como `00-variables.md`.
O script `generate_prompt.py` lerá `00-variables.md` para gerar o prompt de execução.

## 1. Projeto
PROJECT_NAME=
PROJECT_DESCRIPTION=
LANGUAGE=
TIMEZONE=
PROJECT_PREFIX=
# PROJECT_PREFIX: atalho curto e único para o PowerShell Profile (ex: pl, ex, gp).
# Evite conflito com prefixos de outros projetos já no seu $PROFILE.
PROJECT_ROOT=
# PROJECT_ROOT: caminho absoluto da raiz do projeto na sua máquina (ex: C:\Workspace\plurus)

## 2. Usuários e Acesso
USER_ROLES=
AUTH_PROVIDER=

## 2.1. Admin Inicial (Seed Data)
ADMIN_NAME=
ADMIN_USERNAME=
ADMIN_EMAIL=
ADMIN_PASSWORD=

## 3. Infraestrutura Base
USE_DOCKER=
BACKEND_PORT=
BACKEND_PORT_DEV=
AUTH_PORT=
AUTH_PORT_DEV=
FRONTEND_PORT=
FRONTEND_PORT_DEV=
# Frontend ETL — painel React/Vite de gestão ETL (sem backend próprio; deixe vazio se não usar)
FRONTEND_ETL_PORT=
FRONTEND_ETL_PORT_DEV=

## 4. Banco de Dados
# ATENÇÃO: Quando DB_ENABLE_REPLICA=true, certifique-se de que as portas
# DB_PORT_*_REPLICA não colidem com as portas primárias nem entre ambientes.
# Exemplo seguro: prod=5432, prod_replica=5433, dev=5434, dev_replica=5435
DB_VERSION=
DB_LANGUAGE=
DB_ENABLE_ML=
DB_ENABLE_REPLICA=
DB_PORT_PROD=
DB_PORT_PROD_REPLICA=
DB_PORT_DEV=
DB_PORT_DEV_REPLICA=
DOCKER_DB=
DB_NAME_DEV=
DB_NAME_PROD=
DB_USER=
DB_PASSWORD_DEV=
DB_PASSWORD_PROD=

## 5. Cache e Mensageria
CACHE_LAYER=
DOCKER_CACHE=
REDIS_PORT_PROD=
REDIS_PORT_DEV=
QUEUE_LAYER=
DOCKER_QUEUE=
RABBITMQ_AMQP_PORT_PROD=
RABBITMQ_AMQP_PORT_DEV=
RABBITMQ_MGMT_PORT_PROD=
RABBITMQ_MGMT_PORT_DEV=
RABBITMQ_USER_PROD=
RABBITMQ_PASS_PROD=
RABBITMQ_VHOST_PROD=
RABBITMQ_USER_DEV=
RABBITMQ_PASS_DEV=
RABBITMQ_VHOST_DEV=

## 6. IA e ETL
ENABLE_ETL=
ENABLE_AI_LAYER=
EMBEDDING_DB=
DOCKER_EMBEDDING_DB=
QDRANT_PORT_PROD=
QDRANT_PORT_DEV=
QDRANT_GRPC_PORT_PROD=
QDRANT_GRPC_PORT_DEV=
EMBEDDING_MODEL=
AI_MODEL=
AI_AGENTS=
