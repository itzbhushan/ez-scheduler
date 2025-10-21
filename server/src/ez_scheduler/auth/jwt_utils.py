"""JWT utilities for authentication using authlib"""

from typing import Dict

import httpx
from aiocache import Cache, cached
from authlib.jose import JoseError, JsonWebToken
from authlib.jose.errors import InvalidTokenError

from ez_scheduler.auth.models import User
from ez_scheduler.config import config
from ez_scheduler.logging_config import get_logger

logger = get_logger(__name__)


class JWTUtils:
    """JWT token utilities using authlib with JWKS caching"""

    def __init__(self):
        self.jwt = JsonWebToken(["RS256"])
        self.auth0_domain = config.get("auth0_domain")
        self.jwks_url = f"https://{self.auth0_domain}/.well-known/jwks.json"
        self.expected_issuer = f"https://{self.auth0_domain}/"

        if not self.auth0_domain:
            raise ValueError("AUTH0_DOMAIN must be configured")

    @cached(ttl=3600, cache=Cache.MEMORY)
    async def _fetch_jwks(self) -> Dict:
        """
        Fetch JWKS from Auth0 well-known endpoint (cached)

        Returns:
            JWKS dictionary from Auth0
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.jwks_url, timeout=10.0)
                response.raise_for_status()
                jwks_data = response.json()

                logger.info(f"Successfully fetched JWKS from {self.jwks_url}")
                return jwks_data

        except httpx.RequestError as e:
            logger.error(f"Failed to fetch JWKS from {self.jwks_url}: {e}")
            raise InvalidTokenError(f"Unable to fetch JWKS: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching JWKS: {e}")
            raise InvalidTokenError(f"JWKS fetch failed: {e}")

    async def _verify_auth0_token(self, token: str) -> Dict:
        """
        Verify and decode an Auth0 JWT token using cached JWKS

        Args:
            token: JWT token string from Auth0

        Returns:
            Decoded token payload

        Raises:
            InvalidTokenError: If token is invalid or expired
        """
        try:
            # Fetch JWKS (cached)
            jwks = await self._fetch_jwks()

            # Verify and decode token - jwt.decode will automatically find the right key using kid
            claims = self.jwt.decode(token, jwks)

            # Verify issuer matches Auth0 domain
            if claims.get("iss") != self.expected_issuer:
                raise InvalidTokenError(
                    f"Invalid issuer. Expected: {self.expected_issuer}, Got: {claims.get('iss')}"
                )

            return claims

        except JoseError as e:
            logger.error(f"JWT validation failed: {e}")
            raise InvalidTokenError(f"Token validation failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            raise InvalidTokenError(f"Token validation error: {str(e)}")

    async def extract_user(self, token: str) -> User:
        """
        Extract user ID and claims from Auth0 JWT token

        Args:
            token: JWT token string from Auth0

        Returns:
            User object with user_id and claims

        Raises:
            InvalidTokenError: If token is invalid or missing user ID
        """

        claims = await self._verify_auth0_token(token)
        user_id_str = claims.get("sub")

        if not user_id_str:
            raise InvalidTokenError("Token missing 'sub' claim")

        # Extract relevant claims from the token
        user_claims = {
            "iss": claims.get("iss"),
            "aud": claims.get("aud"),
            "exp": claims.get("exp"),
            "iat": claims.get("iat"),
            "scope": claims.get("scope"),
            "permissions": claims.get("permissions", []),
        }

        return User(user_id=user_id_str, claims=user_claims)


# Global JWT utilities instance
jwt_utils = JWTUtils()
