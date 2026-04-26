"""
queue_manager.py
================
Singleton responsável por:
- Publicar mensagens nas filas (pika sync)
- Buscar stats das filas via RabbitMQ Management API (httpx)
- Operações de gestão: purge, depth, declare
"""
import json
import logging
from typing import Optional

import httpx
import pika
import pika.exceptions

from app.core.config import get_settings

logger = logging.getLogger(__name__)

QUEUES = ["extraction_queue", "transform_queue", "processor_queue"]


class QueueManager:
    _instance: Optional["QueueManager"] = None

    def __init__(self):
        self.settings = get_settings()

    @classmethod
    def get_instance(cls) -> "QueueManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── connection ────────────────────────────────────────────────────────────

    def _get_connection(self) -> pika.BlockingConnection:
        credentials = pika.PlainCredentials(
            self.settings.RABBITMQ_USER,
            self.settings.RABBITMQ_PASSWORD,
        )
        params = pika.ConnectionParameters(
            host=self.settings.RABBITMQ_HOST,
            port=self.settings.RABBITMQ_PORT,
            virtual_host=self.settings.RABBITMQ_VHOST,
            credentials=credentials,
            heartbeat=10,
            blocked_connection_timeout=5,
            connection_attempts=3,
            retry_delay=1,
        )
        return pika.BlockingConnection(params)

    # ── declare + publish ─────────────────────────────────────────────────────

    def declare_all_queues(self):
        """Declara todas as filas no startup (idempotente)."""
        conn = self._get_connection()
        ch   = conn.channel()
        for q in QUEUES:
            ch.queue_declare(queue=q, durable=True)
            logger.info("Queue declared: %s", q)
        conn.close()

    def publish(self, queue: str, message: dict) -> None:
        conn = self._get_connection()
        ch   = conn.channel()
        ch.queue_declare(queue=queue, durable=True)
        ch.basic_publish(
            exchange="",
            routing_key=queue,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
        conn.close()

    # ── stats (Management API) ────────────────────────────────────────────────

    def get_queue_stats(self, queue_name: str) -> dict:
        """Busca métricas de uma fila via RabbitMQ Management API."""
        base_url = (
            f"http://{self.settings.RABBITMQ_HOST}"
            f":{self.settings.RABBITMQ_MANAGEMENT_PORT}"
        )
        vhost_enc = self.settings.RABBITMQ_VHOST.replace("/", "%2F")
        try:
            resp = httpx.get(
                f"{base_url}/api/queues/{vhost_enc}/{queue_name}",
                auth=(self.settings.RABBITMQ_USER, self.settings.RABBITMQ_PASSWORD),
                timeout=5.0,
            )
            if resp.status_code == 200:
                d = resp.json()
                ms = d.get("message_stats", {})
                return {
                    "name":                    queue_name,
                    "messages_ready":          d.get("messages_ready", 0),
                    "messages_unacknowledged": d.get("messages_unacknowledged", 0),
                    "messages":                d.get("messages", 0),
                    "consumers":               d.get("consumers", 0),
                    "state":                   d.get("state", "unknown"),
                    "memory":                  d.get("memory", 0),
                    "publish_rate":  ms.get("publish_details", {}).get("rate", 0.0),
                    "deliver_rate":  ms.get("deliver_details", {}).get("rate", 0.0),
                    "ack_rate":      ms.get("ack_details",     {}).get("rate", 0.0),
                }
            logger.warning("Management API returned %d for queue %s", resp.status_code, queue_name)
        except Exception as exc:
            logger.warning("Could not reach RabbitMQ Management API for %s: %s", queue_name, exc)

        return self._empty_stats(queue_name)

    def get_all_queue_stats(self) -> list[dict]:
        return [self.get_queue_stats(q) for q in QUEUES]

    def get_depth(self, queue_name: str) -> int:
        return self.get_queue_stats(queue_name).get("messages_ready", 0)

    # ── operations ────────────────────────────────────────────────────────────

    def purge_queue(self, queue_name: str) -> int:
        """Remove todas as mensagens da fila. Retorna contagem purgada."""
        conn = self._get_connection()
        ch   = conn.channel()
        result = ch.queue_purge(queue=queue_name)
        conn.close()
        purged = result.method.message_count
        logger.info("Purged %d messages from %s", purged, queue_name)
        return purged

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_stats(queue_name: str) -> dict:
        return {
            "name": queue_name, "messages_ready": 0,
            "messages_unacknowledged": 0, "messages": 0,
            "consumers": 0, "state": "unavailable", "memory": 0,
            "publish_rate": 0.0, "deliver_rate": 0.0, "ack_rate": 0.0,
        }
