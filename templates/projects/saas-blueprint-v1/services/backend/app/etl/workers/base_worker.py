"""
base_worker.py
==============
Worker base com lifecycle (start/stop/kill) + consumo de fila via pika.
Cada worker roda em sua própria daemon thread.
"""
import json
import logging
import threading
import time
from abc import abstractmethod
from typing import Optional

import pika
import pika.exceptions

logger = logging.getLogger(__name__)


class BaseWorker:
    def __init__(self, queue_name: str, worker_id: int, settings):
        self.queue_name = queue_name
        self.worker_id  = worker_id
        self.settings   = settings

        self._thread:           Optional[threading.Thread] = None
        self._running:          bool = False
        self._connection:       Optional[pika.BlockingConnection] = None
        self._channel:          Optional[pika.adapters.blocking_connection.BlockingChannel] = None
        self._last_message_at:  Optional[float] = None
        self._processed_count:  int = 0
        self._error_count:      int = 0

    # ── public interface ──────────────────────────────────────────────────────

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        if self.is_alive:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"{self.__class__.__name__}-{self.worker_id}",
        )
        self._thread.start()
        logger.info("▶ Worker %s-%d started", self.__class__.__name__, self.worker_id)

    def stop(self):
        """Graceful stop — aguarda a mensagem atual terminar."""
        self._running = False
        if self._channel:
            try:
                self._channel.stop_consuming()
            except Exception:
                pass
        logger.info("⏹ Worker %s-%d stopping", self.__class__.__name__, self.worker_id)

    def kill(self):
        """Force stop — fecha conexão imediatamente."""
        self._running = False
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
        logger.info("💀 Worker %s-%d killed", self.__class__.__name__, self.worker_id)

    def get_status(self) -> dict:
        return {
            "worker_id":         self.worker_id,
            "worker_type":       self.__class__.__name__,
            "queue":             self.queue_name,
            "is_alive":          self.is_alive,
            "is_running":        self.is_running,
            "processed_count":   self._processed_count,
            "error_count":       self._error_count,
            "last_message_at":   self._last_message_at,
        }

    # ── internal ─────────────────────────────────────────────────────────────

    def _get_connection(self) -> pika.BlockingConnection:
        credentials = pika.PlainCredentials(self.settings.RABBITMQ_USER, self.settings.RABBITMQ_PASS)
        params = pika.ConnectionParameters(
            host=self.settings.RABBITMQ_HOST,
            port=self.settings.RABBITMQ_PORT,
            credentials=credentials,
            heartbeat=60,
            blocked_connection_timeout=30,
        )
        return pika.BlockingConnection(params)

    def _run(self):
        while self._running:
            try:
                self._connection = self._get_connection()
                self._channel    = self._connection.channel()
                self._channel.queue_declare(queue=self.queue_name, durable=True)
                self._channel.basic_qos(prefetch_count=1)
                self._channel.basic_consume(
                    queue=self.queue_name,
                    on_message_callback=self._on_message,
                )
                logger.info(
                    "👂 Worker %s-%d consuming from '%s'",
                    self.__class__.__name__, self.worker_id, self.queue_name,
                )
                self._channel.start_consuming()
            except pika.exceptions.ConnectionClosedByBroker:
                if self._running:
                    logger.warning("Worker %s-%d connection closed by broker, retrying in 5s…", self.__class__.__name__, self.worker_id)
                    time.sleep(5)
            except Exception as exc:
                if self._running:
                    logger.warning("Worker %s-%d error, retrying in 5s: %s", self.__class__.__name__, self.worker_id, exc)
                    time.sleep(5)

    def _on_message(self, ch, method, _properties, body):
        try:
            message = json.loads(body)
            self._last_message_at = time.time()
            self.process(message)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            self._processed_count += 1
        except Exception as exc:
            logger.error("Worker %s-%d failed to process message: %s", self.__class__.__name__, self.worker_id, exc, exc_info=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            self._error_count += 1

    @abstractmethod
    def process(self, message: dict) -> None:
        """Implementar em cada worker concreto."""
