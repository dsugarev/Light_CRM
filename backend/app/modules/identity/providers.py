"""Authentication providers (FR-AUTH-06).

R1 ships the local password provider. An OpenID Connect provider (Microsoft
Entra ID) can be added later and registered under its name; users are then
matched on (auth_provider, external_subject) without changing other modules.
"""

from typing import Protocol

from app.modules.identity.models import User
from app.modules.identity.passwords import verify_password


class AuthProvider(Protocol):
    name: str

    async def verify_credentials(self, user: User, password: str) -> bool: ...


class LocalPasswordProvider:
    name = "local"

    async def verify_credentials(self, user: User, password: str) -> bool:
        if user.password_hash is None:
            return False
        return await verify_password(user.password_hash, password)


PROVIDERS: dict[str, AuthProvider] = {LocalPasswordProvider.name: LocalPasswordProvider()}
