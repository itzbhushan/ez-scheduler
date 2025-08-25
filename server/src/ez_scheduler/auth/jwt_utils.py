"""JWT utilities for authentication using authlib"""

import logging
from typing import Dict

import httpx
from authlib.jose import JoseError, JsonWebKey, JsonWebToken
from authlib.jose.errors import InvalidTokenError
from deprecated import deprecated

from ez_scheduler.auth.models import UserClaims
from ez_scheduler.config import config

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)

# TODO: Add caching for JWKS to avoid fetching on every request


class JWTUtils:
    """JWT token utilities using authlib"""

    def __init__(self):
        self.jwt = JsonWebToken(["RS256"])
        self.auth0_domain = config.get("auth0_domain")
        self.algorithm = "RS256"
        self.token_expire_hours = 24

        if not self.auth0_domain:
            raise ValueError("AUTH0_DOMAIN must be configured")

    async def _fetch_jwks(self) -> Dict:
        """
        Fetch JWKS from Auth0 well-known endpoint

        Returns:
            JWKS dictionary from Auth0
        """
        jwks_url = f"https://{self.auth0_domain}/.well-known/jwks.json"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(jwks_url, timeout=10.0)
                response.raise_for_status()
                jwks_data = response.json()

                logger.info(f"Successfully fetched JWKS from {jwks_url}")
                return jwks_data

        except httpx.RequestError as e:
            logger.error(f"Failed to fetch JWKS from {jwks_url}: {e}")
            raise InvalidTokenError(f"Unable to fetch JWKS: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching JWKS: {e}")
            raise InvalidTokenError(f"JWKS fetch failed: {e}")

    async def verify_auth0_token(self, token: str) -> Dict:
        """
        Verify and decode an Auth0 JWT token using JWKS

        Args:
            token: JWT token string from Auth0

        Returns:
            Decoded token payload

        Raises:
            InvalidTokenError: If token is invalid or expired
        """
        try:
            # Fetch JWKS
            jwks = await self._fetch_jwks()

            # Verify and decode token - jwt.decode will automatically find the right key using kid
            claims = self.jwt.decode(token, jwks)

            # Verify issuer matches Auth0 domain
            expected_issuer = f"https://{self.auth0_domain}/"
            if claims.get("iss") != expected_issuer:
                raise InvalidTokenError(
                    f"Invalid issuer. Expected: {expected_issuer}, Got: {claims.get('iss')}"
                )

            logger.info(
                f"Successfully verified Auth0 token for user: {claims.get('sub')}"
            )
            return claims

        except JoseError as e:
            logger.error(f"JWT validation failed: {e}")
            raise InvalidTokenError(f"Token validation failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {e}")
            raise InvalidTokenError(f"Token validation error: {str(e)}")

    @deprecated(reason="Legacy admin method")
    def verify_token(self, token: str) -> Dict:
        """
        Verify and decode a JWT token

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            InvalidTokenError: If token is invalid or expired
        """

        logger.warning(f"Verifying token: {token}")

        try:
            claims = self.jwt.decode(token, self.secret_key)

            # Verify issuer
            if claims.get("iss") != self.issuer:
                raise InvalidTokenError("Invalid issuer")

            return claims

        except JoseError as e:
            raise InvalidTokenError(f"Token validation failed: {str(e)}")

    async def extract_user(self, token: str) -> UserClaims:
        """
        Extract user ID and claims from Auth0 JWT token

        Args:
            token: JWT token string from Auth0

        Returns:
            UserClaims object with user_id and claims

        Raises:
            InvalidTokenError: If token is invalid or missing user ID
        """

        claims = await self.verify_auth0_token(token)
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

        return UserClaims(user_id=user_id_str, claims=user_claims)


# Global JWT utilities instance
jwt_utils = JWTUtils()
