import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Log level from env — DEBUG in dev, INFO in prod (injected by gus.ps1 via APP_ENV)
_log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, _log_level_str, logging.INFO)

SERVICE_NAME = "backend"
_logging_configured = False


def setup_logging(force_reconfigure: bool = False) -> None:
    """Configura o logger raiz da aplicação."""
    global _logging_configured
    if _logging_configured and not force_reconfigure:
        return

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console — all levels at or above LOG_LEVEL
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File — separate file per env, INFO+ only (DEBUG stays console-only)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    app_env = os.environ.get("APP_ENV", "prod")
    file_handler = RotatingFileHandler(
        f"logs/{SERVICE_NAME}.{app_env}.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    root_logger.setLevel(LOG_LEVEL)
    _silence_third_party_loggers()
    _logging_configured = True


def _silence_third_party_loggers() -> None:
    """Reduz verbosidade de bibliotecas de terceiros."""
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    # pika — silencia o ruído de connection workflow e socket (mantém só WARNING+)
    logging.getLogger("pika").setLevel(logging.WARNING)
    # sqlalchemy — echo=False sempre no engine; aqui decidimos o nível via SQL_ECHO
    # SQL_ECHO=true em dev habilita queries no log sem duplicar (sem handler próprio do SA)
    _sql_echo = os.environ.get("SQL_ECHO", "false").lower() in ("1", "true", "yes")
    _sa_level = logging.INFO if _sql_echo else logging.CRITICAL
    logging.getLogger("sqlalchemy").setLevel(_sa_level)
    logging.getLogger("sqlalchemy.engine").setLevel(_sa_level)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.CRITICAL)  # pool sempre silenciado


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retorna uma instância de logger para o módulo."""
    if name is None:
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "unknown")
        else:
            name = "unknown"
    return logging.getLogger(name)


class LoggerMixin:
    """Mixin para adicionar logging a classes."""

    @property
    def logger(self) -> logging.Logger:
        return get_logger(f"{self.__class__.__module__}.{self.__class__.__name__}")
