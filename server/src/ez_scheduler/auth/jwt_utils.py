"""JWT utilities for authentication using authlib"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from authlib.jose import JoseError, JsonWebToken
from authlib.jose.errors import InvalidTokenError

from ez_scheduler.config import config


class JWTUtils:
    """JWT token utilities using authlib"""

    def __init__(self):
        self.jwt = JsonWebToken(["HS256"])
        self.secret_key = config.get("jwt_secret_key")
        self.algorithm = "HS256"
        self.issuer = "ez-scheduler"
        self.token_expire_hours = 24

        if not self.secret_key:
            raise ValueError("JWT_SECRET_KEY must be configured")

    def create_access_token(self, user_id: uuid.UUID) -> str:
        """
        Create a JWT access token

        Args:
            user_id: User UUID

        Returns:
            JWT token string
        """
        expire = datetime.now(timezone.utc) + timedelta(hours=self.token_expire_hours)

        payload = {
            "sub": str(user_id),  # Subject (user ID)
            "iss": self.issuer,  # Issuer
            "exp": expire,  # Expiration time
            "iat": datetime.now(timezone.utc),  # Issued at
        }

        header = {"alg": self.algorithm}

        return self.jwt.encode(header, payload, self.secret_key)

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
        try:
            claims = self.jwt.decode(token, self.secret_key)

            # Verify issuer
            if claims.get("iss") != self.issuer:
                raise InvalidTokenError("Invalid issuer")

            return claims

        except JoseError as e:
            raise InvalidTokenError(f"Token validation failed: {str(e)}")

    def extract_user_id(self, token: str) -> uuid.UUID:
        """
        Extract user ID from JWT token

        Args:
            token: JWT token string

        Returns:
            User UUID

        Raises:
            InvalidTokenError: If token is invalid or missing user ID
        """
        claims = self.verify_token(token)
        user_id_str = claims.get("sub")

        try:
            return uuid.UUID(user_id_str)
        except ValueError:
            raise InvalidTokenError("Invalid user ID format in token")


# Global JWT utilities instance
jwt_utils = JWTUtils()
