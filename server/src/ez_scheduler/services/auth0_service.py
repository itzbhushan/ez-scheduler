"""Auth0 Management API service for fetching user details"""

import asyncio
import logging
from typing import Optional

import httpx
from aiocache import Cache, cached

from ez_scheduler.config import config

logger = logging.getLogger(__name__)


class Auth0Service:
    """Service for interacting with Auth0 Management API"""

    def __init__(self):
        self.auth0_domain = config.get("auth0_domain")
        self.client_id = config.get("auth0_management_client_id")
        self.client_secret = config.get("auth0_management_client_secret")

        # Check if credentials are configured
        self.is_configured = bool(
            self.auth0_domain and self.client_id and self.client_secret
        )

        # Lock for thread-safe token refresh operations
        self._token_refresh_lock = asyncio.Lock()

        if self.is_configured:
            self.token_url = f"https://{self.auth0_domain}/oauth/token"
            self.users_api_url = f"https://{self.auth0_domain}/api/v2/users"
        else:
            logger.warning(
                "Auth0 Management API credentials not configured. "
                "Creator notifications will be disabled."
            )

    @cached(ttl=43200, cache=Cache.MEMORY)
    async def _get_management_token(self) -> str:
        """
        Get Auth0 Management API token (cached for half a day)

        Returns:
            Management API access token

        Raises:
            RuntimeError: If token request fails
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    json={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "audience": f"https://{self.auth0_domain}/api/v2/",
                        "grant_type": "client_credentials",
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                token_data = response.json()

                logger.info("Successfully obtained Auth0 Management API token")
                return token_data["access_token"]

        except httpx.RequestError as e:
            logger.error(f"Failed to get Auth0 management token: {e}")
            raise RuntimeError(f"Auth0 token request failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting Auth0 token: {e}")
            raise RuntimeError(f"Auth0 token error: {e}")

    async def _clear_management_token_cache(self) -> None:
        """Clear the cached management token to force a fresh token fetch"""
        try:
            cache = Cache.MEMORY
            # Generate the same cache key that the @cached decorator uses
            cache_key = f"_get_management_token:"
            await cache.delete(cache_key)
            logger.info("Cleared Auth0 management token cache")
        except Exception as e:
            logger.warning(f"Failed to clear management token cache: {e}")

    @cached(ttl=86400, cache=Cache.MEMORY)  # Cache for 1 day (24 hours)
    async def get_user_email(self, user_id: str) -> Optional[str]:
        """
        Get user email from Auth0 by user ID

        Args:
            user_id: Auth0 user ID (e.g., "auth0|123456")

        Returns:
            User email address if found, None if not found or no email

        Raises:
            RuntimeError: If API request fails
        """
        # Check if service is configured
        if not self.is_configured:
            logger.warning(
                "Auth0 Management API not configured, cannot fetch user email"
            )
            return None

        try:
            return await self._fetch_user_email_with_retry(user_id)
        except httpx.RequestError as e:
            logger.error(f"Failed to fetch user {user_id} from Auth0: {e}")
            raise RuntimeError(f"Auth0 user fetch failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching user {user_id}: {e}")
            raise RuntimeError(f"Auth0 user fetch error: {e}")

    async def _fetch_user_email_with_retry(self, user_id: str) -> Optional[str]:
        """
        Fetch user email with thread-safe retry logic for 401 errors.

        Args:
            user_id: Auth0 user ID

        Returns:
            User email if found, None if not found
        """
        # First attempt without lock
        try:
            result = await self._make_user_api_call(user_id)
            if result is not None:  # Success or 404 (user not found)
                return result
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 401:
                raise  # Re-raise non-401 errors immediately

        # 401 error detected - use lock for thread-safe token refresh
        async with self._token_refresh_lock:
            logger.info(
                f"Acquired lock for token refresh due to 401 error for user {user_id}"
            )

            # Try once more in case another thread already refreshed the token
            try:
                result = await self._make_user_api_call(user_id)
                if result is not None:
                    logger.info(
                        f"Successfully fetched user {user_id} after lock acquisition"
                    )
                    return result
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 401:
                    raise  # Re-raise non-401 errors

            # Still getting 401, clear cache and try once more
            logger.info("Still receiving 401, clearing token cache and retrying")
            await self._clear_management_token_cache()

            # Final attempt with fresh token
            return await self._make_user_api_call(user_id)

    async def _make_user_api_call(self, user_id: str) -> Optional[str]:
        """
        Make the actual API call to fetch user email.

        Args:
            user_id: Auth0 user ID

        Returns:
            User email if found, None if user not found (404)

        Raises:
            httpx.HTTPStatusError: For HTTP errors (including 401)
        """
        # Get management token
        token = await self._get_management_token()

        # Fetch user details
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.users_api_url}/{user_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"fields": "email"},
                timeout=10.0,
            )

            if response.status_code == 404:
                logger.warning(f"User {user_id} not found in Auth0")
                return None

            response.raise_for_status()  # This will raise HTTPStatusError for non-2xx responses
            user_data = response.json()

            email = user_data.get("email")
            logger.info(f"Successfully fetched email for user {user_id}")
            return email


# Global Auth0 service instance
auth0_service = Auth0Service()
