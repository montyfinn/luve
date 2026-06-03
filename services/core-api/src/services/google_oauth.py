"""Google OAuth 2.0 / OpenID Connect client (server-side authorization code flow).

Hand-rolled on ``httpx`` + ``python-jose`` (both already in the core-api
dependency set) rather than a new framework dependency, matching the repo's
raw-client idiom (see grading-worker ``GroqClient``). The ``client_secret`` is
used only server-side; no secret, authorization code, ID token, or raw claim is
ever placed in an exception message or log line.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from jose import jwt
from jose.exceptions import JWTError

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
OIDC_SCOPE = "openid email profile"


class GoogleOAuthError(Exception):
    """Base error for the Google OAuth flow. Messages must stay secret-free."""


class GoogleTokenExchangeError(GoogleOAuthError):
    """The authorization-code -> token exchange failed."""


class GoogleIdentityError(GoogleOAuthError):
    """The ID token could not be verified."""


class GoogleEmailUnverifiedError(GoogleIdentityError):
    """The Google account email is absent or not verified."""


class GoogleAccountConflictError(Exception):
    """A verified Google identity cannot be linked under the no-auto-link policy.

    ``code`` is a safe, user-facing token: ``account_exists`` or ``link_conflict``.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str | None
    hd: str | None


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    return secrets.token_urlsafe(16)


def build_authorize_url(*, client_id: str, redirect_uri: str, state: str, nonce: str) -> str:
    """Build the Google authorization URL for a top-level browser redirect."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": OIDC_SCOPE,
        "state": state,
        "nonce": nonce,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"


class GoogleOAuthClient:
    """Server-side Google OIDC client. Construct from settings per request."""

    def __init__(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        redirect_uri: str | None,
        allowed_hd: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not client_id or not client_secret or not redirect_uri:
            raise GoogleOAuthError("Google OAuth client is not configured")
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._allowed_hd = allowed_hd
        self._timeout = timeout_seconds

    async def _exchange_code(self, code: str) -> str:
        data = {
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self._redirect_uri,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(GOOGLE_TOKEN_ENDPOINT, data=data)
        except httpx.HTTPError as exc:
            raise GoogleTokenExchangeError("Google token exchange transport error") from exc
        if response.status_code != 200:
            raise GoogleTokenExchangeError(
                f"Google token endpoint returned status {response.status_code}"
            )
        try:
            id_token = response.json().get("id_token")
        except ValueError as exc:
            raise GoogleTokenExchangeError("Google token response was not valid JSON") from exc
        if not id_token:
            raise GoogleTokenExchangeError("Google token response missing id_token")
        return id_token

    async def _fetch_jwks(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(GOOGLE_JWKS_URI)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GoogleIdentityError("Failed to fetch Google JWKS") from exc

    def verify_id_token(self, id_token: str, jwks: dict, *, expected_nonce: str) -> GoogleIdentity:
        """Verify signature (JWKS/RS256) + iss/aud/exp/nonce/email_verified/hd.

        Pure and synchronous so it is unit-testable without network access.
        """
        try:
            claims = jwt.decode(
                id_token,
                jwks,
                algorithms=["RS256"],
                audience=self._client_id,
                options={"verify_at_hash": False},
            )
        except JWTError as exc:
            raise GoogleIdentityError("Google ID token verification failed") from exc

        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise GoogleIdentityError("Google ID token issuer mismatch")
        if not secrets.compare_digest(str(claims.get("nonce", "")), expected_nonce):
            raise GoogleIdentityError("Google ID token nonce mismatch")

        email = claims.get("email")
        if not email or claims.get("email_verified") is not True:
            raise GoogleEmailUnverifiedError("Google account email is not verified")

        hd = claims.get("hd")
        if self._allowed_hd and hd != self._allowed_hd:
            raise GoogleIdentityError("Google account domain is not allowed")

        sub = claims.get("sub")
        if not sub:
            raise GoogleIdentityError("Google ID token missing subject")

        return GoogleIdentity(
            sub=str(sub),
            email=str(email),
            email_verified=True,
            name=claims.get("name"),
            hd=hd,
        )

    async def authenticate(self, *, code: str, expected_nonce: str) -> GoogleIdentity:
        """Exchange the code, fetch JWKS, and return the verified identity."""
        id_token = await self._exchange_code(code)
        jwks = await self._fetch_jwks()
        return self.verify_id_token(id_token, jwks, expected_nonce=expected_nonce)
