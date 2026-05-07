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


def get_email(token: str) -> str | None:
    """Return the email from a valid Cognito ID token, or None.

    The ID token (not the access token) contains the email attribute.
    """
    claims = verify_token(token)
    if not claims:
        return None
    return claims.get('email')


def get_username(token: str) -> str | None:
    """Return email from ID token, falling back to cognito:username."""
    claims = verify_token(token)
    if not claims:
        return None
    return claims.get('email') or claims.get('cognito:username') or claims.get('username')


def authenticate_user(username: str, password: str) -> dict | None:
    """Call Cognito USER_PASSWORD_AUTH. Returns tokens dict or None on failure.

    Requires ALLOW_USER_PASSWORD_AUTH enabled on the Cognito app client.
    Returns: {access_token, id_token, refresh_token, expires_in} or None.
    """
    if not _is_configured():
        return None
    url = f'https://cognito-idp.{COGNITO_REGION}.amazonaws.com/'
    headers = {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
    }
    body = {
        'AuthFlow': 'USER_PASSWORD_AUTH',
        'AuthParameters': {'USERNAME': username, 'PASSWORD': password},
        'ClientId': COGNITO_APP_CLIENT_ID,
    }
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning('Cognito auth failed: %s %s', resp.status_code, resp.text)
            return None
        result = resp.json().get('AuthenticationResult', {})
        return {
            'access_token': result.get('AccessToken'),
            'id_token': result.get('IdToken'),
            'refresh_token': result.get('RefreshToken'),
            'expires_in': result.get('ExpiresIn', 3600),
        }
    except Exception as e:
        logger.error('Cognito authenticate_user error: %s', e)
        return None


def is_configured() -> bool:
    return _is_configured()
