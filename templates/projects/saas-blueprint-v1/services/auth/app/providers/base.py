from abc import ABC, abstractmethod
from typing import Any, Dict


class AuthProvider(ABC):
    """Interface base para providers de autenticação.

    Implementações concretas: LocalAuthProvider, Auth0Provider, OktaProvider, etc.
    Permite trocar o mecanismo de auth sem alterar o código de negócio.
    """

    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Valida credenciais e retorna dados do usuário.

        Args:
            credentials: dict com email/password (local) ou token (SSO).

        Returns:
            Dicionário com dados do usuário autenticado.

        Raises:
            ValueError: Se as credenciais forem inválidas.
        """

    @abstractmethod
    def generate_tokens(self, user_data: Dict[str, Any]) -> Dict[str, str]:
        """Gera access_token e refresh_token.

        Returns:
            {'access_token': str, 'token_type': 'bearer'}
        """

    @abstractmethod
    def validate_token(self, token: str) -> Dict[str, Any]:
        """Valida um token JWT e retorna o payload.

        Raises:
            ValueError: Se o token for inválido ou expirado.
        """
