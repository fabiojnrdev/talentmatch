import hmac

from fastapi import Depends, Header, HTTPException

from app.config import Settings, get_settings


def require_client(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Autentica por API key e devolve o client_id (escopo de propriedade dos dados)."""
    matched: str | None = None
    if x_api_key:
        for client_id, secret in settings.api_key_pairs:
            if hmac.compare_digest(secret.encode(), x_api_key.encode()):
                matched = client_id
    if matched is None:
        raise HTTPException(401, "API key ausente ou inválida.", headers={"WWW-Authenticate": "ApiKey"})
    return matched
