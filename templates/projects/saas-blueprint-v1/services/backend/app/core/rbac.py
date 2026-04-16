from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEW = "view"


# Hierarquia de roles: maior valor = maior privilégio.
# Usado para comparar se user.role >= page.min_role.
ROLE_HIERARCHY: dict[str, int] = {
    Role.VIEW:  0,
    Role.USER:  1,
    Role.ADMIN: 2,
}


def role_level(role: str) -> int:
    """Retorna o nível numérico do role. Role desconhecido → -1 (sem acesso)."""
    return ROLE_HIERARCHY.get(role, -1)
