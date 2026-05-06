import logging
import os
import time

import requests
from jose import jwt, jwk

logger = logging.getLogger(__name__)

COGNITO_REGION = os.environ.get('COGNITO_REGION', '')
COGNITO_POOL_ID = os.environ.get('COGNITO_POOL_ID', '')
COGNITO_APP_CLIENT_ID = os.environ.get('COGNITO_APP_CLIENT_ID', '')

_jwks_cache: list = []
_jwks_fetched_at: float = 0
_JWKS_TTL = 3600  # re-fetch public keys every hour


def _is_configured() -> bool:
    return bool(COGNITO_REGION and COGNITO_POOL_ID and COGNITO_APP_CLIENT_ID)


def _get_jwks() -> list:
    global _jwks_cache, _jwks_fetched_at
    if _jwks_cache and time.time() - _jwks_fetched_at < _JWKS_TTL:
        return _jwks_cache
    url = (f'https://cognito-idp.{COGNITO_REGION}.amazonaws.com'
           f'/{COGNITO_POOL_ID}/.well-known/jwks.json')
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    _jwks_cache = resp.json()['keys']
    _jwks_fetched_at = time.time()
    return _jwks_cache


def verify_token(token: str) -> dict | None:
    """Validate a Cognito JWT. Returns the claims dict, or None if invalid."""
    if not _is_configured():
        return None
    try:
        headers = jwt.get_unverified_headers(token)
        kid = headers.get('kid')
        key_data = next((k for k in _get_jwks() if k['kid'] == kid), None)
        if not key_data:
            return None
        public_key = jwk.construct(key_data)
        claims = jwt.decode(
            token,
            public_key,
            algorithms=['RS256'],
            audience=COGNITO_APP_CLIENT_ID,
            issuer=(f'https://cognito-idp.{COGNITO_REGION}.amazonaws.com'
                    f'/{COGNITO_POOL_ID}'),
        )
        return claims
    except Exception as e:
        logger.debug('Cognito token validation failed: %s', e)
        return None


def get_username(token: str) -> str | None:
    """Return the username from a valid Cognito token, or None."""
    claims = verify_token(token)
    if not claims:
        return None
    return claims.get('cognito:username') or claims.get('username')


def is_configured() -> bool:
    return _is_configured()
