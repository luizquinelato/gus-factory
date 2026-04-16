# Project Variables (Template)

Fill in all fields below and save a copy as `00-variables.md`.
The `generate_prompt.py` script will read `00-variables.md` to generate the execution prompt.

## 1. Project
PROJECT_NAME=
PROJECT_DESCRIPTION=
LANGUAGE=
TIMEZONE=
PROJECT_PREFIX=
# PROJECT_PREFIX: short unique alias for the PowerShell Profile (e.g.: pl, ex, gp).
# Avoid conflicts with prefixes from other projects already in your $PROFILE.
PROJECT_ROOT=
# PROJECT_ROOT: absolute path to the project root on your machine (e.g.: C:\Workspace\plurus)

## 2. Users and Access
USER_ROLES=
AUTH_PROVIDER=

## 2.1. Initial Admin (Seed Data)
ADMIN_NAME=
ADMIN_USERNAME=
ADMIN_EMAIL=
ADMIN_PASSWORD=

## 3. Base Infrastructure
USE_DOCKER=
BACKEND_PORT=
BACKEND_PORT_DEV=
AUTH_PORT=
AUTH_PORT_DEV=
FRONTEND_PORT=
FRONTEND_PORT_DEV=
# Frontend ETL — React/Vite ETL management panel (no own backend; leave empty if not used)
FRONTEND_ETL_PORT=
FRONTEND_ETL_PORT_DEV=

## 4. Database
# NOTE: When DB_ENABLE_REPLICA=true, ensure that DB_PORT_*_REPLICA ports
# do not collide with primary ports or between environments.
# Safe example: prod=5432, prod_replica=5433, dev=5434, dev_replica=5435
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

## 5. Cache and Messaging
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

## 6. AI and ETL
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
