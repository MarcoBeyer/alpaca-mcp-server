"""
GitHub OAuth Provider for FastMCP
Implements GitHub OAuth 2.1 authentication for MCP servers.
"""

import os
import json
import httpx
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlencode, parse_qs
from dataclasses import dataclass

from mcp.server.auth.provider import (
    OAuthAuthorizationServerProvider,
    AuthorizationCode,
    AccessToken,
    RefreshToken,
    AuthorizationParams,
    OAuthToken,
    TokenError,
    TokenErrorCode,
    AuthorizeError,
    AuthorizationErrorCode
)


@dataclass
class GitHubProviderConfig:
    """Configuration for GitHub OAuth Provider."""
    client_id: str
    client_secret: str
    base_url: str
    redirect_path: str = "/auth/callback"
    allowed_email: Optional[str] = None
    scopes: str = "user:email"


class GitHubProvider(OAuthAuthorizationServerProvider[AuthorizationCode, AccessToken, RefreshToken]):
    """GitHub OAuth 2.1 Provider for FastMCP."""
    
    def __init__(self, client_id: str, client_secret: str, base_url: str, 
                 redirect_path: str = "/auth/callback", allowed_email: Optional[str] = None):
        self.config = GitHubProviderConfig(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url.rstrip('/'),
            redirect_path=redirect_path,
            allowed_email=allowed_email
        )
        
        # GitHub OAuth URLs
        self.authorize_url = "https://github.com/login/oauth/authorize"
        self.token_url = "https://github.com/login/oauth/access_token"
        self.api_base_url = "https://api.github.com"
        
    async def get_authorization_url(self, params: AuthorizationParams) -> str:
        """Generate GitHub authorization URL."""
        redirect_uri = f"{self.config.base_url}{self.config.redirect_path}"
        
        oauth_params = {
            'client_id': self.config.client_id,
            'redirect_uri': redirect_uri,
            'scope': self.config.scopes,
            'state': params.state,
            'response_type': 'code'
        }
        
        return f"{self.authorize_url}?{urlencode(oauth_params)}"
    
    async def exchange_authorization_code(self, code: AuthorizationCode) -> OAuthToken:
        """Exchange authorization code for access token."""
        redirect_uri = f"{self.config.base_url}{self.config.redirect_path}"
        
        data = {
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'code': code,
            'redirect_uri': redirect_uri
        }
        
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Alpaca-MCP-Server/1.0'
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.token_url, data=data, headers=headers)
                response.raise_for_status()
                token_data = response.json()
                
                if 'error' in token_data:
                    raise TokenError(
                        error=TokenErrorCode.INVALID_GRANT,
                        error_description=token_data.get('error_description', 'Authorization code exchange failed')
                    )
                
                access_token = token_data.get('access_token')
                if not access_token:
                    raise TokenError(
                        error=TokenErrorCode.INVALID_GRANT,
                        error_description='No access token received'
                    )
                
                # Validate user if email restriction is set
                if self.config.allowed_email:
                    user_valid, user_info = await self._validate_user(access_token)
                    if not user_valid:
                        raise TokenError(
                            error=TokenErrorCode.ACCESS_DENIED,
                            error_description=f'Access denied. Only {self.config.allowed_email} is allowed.'
                        )
                
                return OAuthToken(
                    access_token=AccessToken(access_token),
                    token_type=token_data.get('token_type', 'bearer'),
                    expires_in=token_data.get('expires_in'),
                    refresh_token=RefreshToken(token_data.get('refresh_token')) if token_data.get('refresh_token') else None,
                    scope=token_data.get('scope')
                )
                
            except httpx.HTTPError as e:
                raise TokenError(
                    error=TokenErrorCode.SERVER_ERROR,
                    error_description=f'Failed to exchange authorization code: {str(e)}'
                )
    
    async def _validate_user(self, access_token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Validate user against allowed email."""
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Alpaca-MCP-Server/1.0'
        }
        
        async with httpx.AsyncClient() as client:
            try:
                # Get user info
                user_response = await client.get(f"{self.api_base_url}/user", headers=headers)
                user_response.raise_for_status()
                user_info = user_response.json()
                
                # Get user emails
                emails_response = await client.get(f"{self.api_base_url}/user/emails", headers=headers)
                emails_response.raise_for_status()
                emails = emails_response.json()
                
                # Find primary email
                primary_email = None
                for email_data in emails:
                    if email_data.get('primary', False):
                        primary_email = email_data.get('email')
                        break
                
                if not primary_email:
                    primary_email = user_info.get('email')
                
                # Check if email matches allowed email
                if self.config.allowed_email and primary_email != self.config.allowed_email:
                    return False, None
                
                return True, {
                    'login': user_info.get('login'),
                    'email': primary_email,
                    'name': user_info.get('name'),
                    'id': user_info.get('id')
                }
                
            except httpx.HTTPError:
                return False, None
    
    async def refresh_access_token(self, refresh_token: RefreshToken) -> OAuthToken:
        """Refresh access token (GitHub doesn't support refresh tokens in the traditional sense)."""
        raise TokenError(
            error=TokenErrorCode.UNSUPPORTED_GRANT_TYPE,
            error_description="GitHub OAuth does not support refresh tokens"
        )
    
    async def revoke_token(self, token: AccessToken) -> None:
        """Revoke access token."""
        # GitHub doesn't have a standard revocation endpoint for OAuth apps
        # The token will expire naturally or can be revoked through GitHub's UI
        pass
    
    async def introspect_token(self, token: AccessToken) -> Dict[str, Any]:
        """Introspect token by calling GitHub API."""
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Alpaca-MCP-Server/1.0'
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.api_base_url}/user", headers=headers)
                if response.status_code == 401:
                    return {'active': False}
                
                response.raise_for_status()
                user_info = response.json()
                
                return {
                    'active': True,
                    'client_id': self.config.client_id,
                    'username': user_info.get('login'),
                    'scope': self.config.scopes,
                    'sub': str(user_info.get('id')),
                    'aud': self.config.base_url
                }
                
            except httpx.HTTPError:
                return {'active': False}


def create_github_provider_from_env() -> Optional[GitHubProvider]:
    """Create GitHubProvider from environment variables."""
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    base_url = os.getenv("OAUTH_BASE_URL", "http://localhost:8000")
    allowed_email = os.getenv("OAUTH_ALLOWED_EMAIL")
    
    if not client_id or not client_secret:
        return None
    
    return GitHubProvider(
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        allowed_email=allowed_email
    )