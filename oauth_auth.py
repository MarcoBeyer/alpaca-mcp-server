"""
OAuth 2.1 Authentication Module for Alpaca MCP Server
Provides GitHub OAuth authentication with user email validation.
"""

import os
import json
from typing import Optional, Dict, Any
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth
from authlib.oauth2 import OAuth2Error
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Route
from itsdangerous import URLSafeTimedSerializer


class OAuthConfig:
    """OAuth configuration from environment variables."""
    
    def __init__(self):
        self.enabled = os.getenv("OAUTH_ENABLED", "false").lower() == "true"
        self.github_client_id = os.getenv("GITHUB_CLIENT_ID")
        self.github_client_secret = os.getenv("GITHUB_CLIENT_SECRET")
        self.allowed_email = os.getenv("OAUTH_ALLOWED_EMAIL", "mbeyer2@gmail.com")
        self.secret_key = os.getenv("OAUTH_SECRET_KEY", "dev-secret-key-change-in-production")
        self.redirect_url = os.getenv("OAUTH_REDIRECT_URL", "http://localhost:8000/auth/callback")
        
    def is_valid(self) -> bool:
        """Check if OAuth configuration is valid."""
        if not self.enabled:
            return False
        return bool(
            self.github_client_id and 
            self.github_client_secret and 
            self.allowed_email and
            self.secret_key
        )


class OAuthManager:
    """Manages OAuth 2.1 authentication flow."""
    
    def __init__(self, config: OAuthConfig):
        self.config = config
        self.oauth = OAuth()
        self.serializer = URLSafeTimedSerializer(config.secret_key)
        
        if config.is_valid():
            self.oauth.register(
                name='github',
                client_id=config.github_client_id,
                client_secret=config.github_client_secret,
                access_token_url='https://github.com/login/oauth/access_token',
                authorize_url='https://github.com/login/oauth/authorize',
                api_base_url='https://api.github.com/',
                client_kwargs={'scope': 'user:email'},
            )
    
    async def get_login_url(self, request: Request) -> str:
        """Generate GitHub OAuth login URL."""
        if not self.config.is_valid():
            raise ValueError("OAuth not properly configured")
        
        github = self.oauth.github
        redirect_uri = self.config.redirect_url
        return await github.authorize_redirect(request, redirect_uri)
    
    async def handle_callback(self, request: Request) -> Dict[str, Any]:
        """Handle OAuth callback and validate user."""
        if not self.config.is_valid():
            raise ValueError("OAuth not properly configured")
        
        try:
            github = self.oauth.github
            token = await github.authorize_access_token(request)
            
            # Get user info from GitHub
            resp = await github.get('user', token=token)
            user_info = resp.json()
            
            # Get user email (may be private)
            email_resp = await github.get('user/emails', token=token)
            emails = email_resp.json()
            
            # Find primary email
            primary_email = None
            for email_data in emails:
                if email_data.get('primary', False):
                    primary_email = email_data.get('email')
                    break
            
            if not primary_email:
                # Fallback to public email if no primary found
                primary_email = user_info.get('email')
            
            # Validate allowed email
            if primary_email != self.config.allowed_email:
                return {
                    'success': False,
                    'error': f'Unauthorized email: {primary_email}. Only {self.config.allowed_email} is allowed.',
                    'user_info': None
                }
            
            return {
                'success': True,
                'error': None,
                'user_info': {
                    'login': user_info.get('login'),
                    'email': primary_email,
                    'name': user_info.get('name'),
                    'id': user_info.get('id')
                }
            }
            
        except OAuth2Error as e:
            return {
                'success': False,
                'error': f'OAuth error: {str(e)}',
                'user_info': None
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Authentication error: {str(e)}',
                'user_info': None
            }
    
    def create_session_token(self, user_info: Dict[str, Any]) -> str:
        """Create a secure session token."""
        return self.serializer.dumps(user_info)
    
    def verify_session_token(self, token: str, max_age: int = 86400) -> Optional[Dict[str, Any]]:
        """Verify and decode session token. Default max_age is 24 hours."""
        try:
            return self.serializer.loads(token, max_age=max_age)
        except Exception:
            return None


def create_oauth_routes(oauth_manager: OAuthManager) -> list:
    """Create OAuth-related routes."""
    
    async def login_page(request: Request):
        """Display login page."""
        if not oauth_manager.config.is_valid():
            return HTMLResponse("""
                <html><body>
                    <h1>OAuth Not Configured</h1>
                    <p>Please configure OAuth environment variables:</p>
                    <ul>
                        <li>OAUTH_ENABLED=true</li>
                        <li>GITHUB_CLIENT_ID=your_client_id</li>
                        <li>GITHUB_CLIENT_SECRET=your_client_secret</li>
                        <li>OAUTH_ALLOWED_EMAIL=mbeyer2@gmail.com (or desired email)</li>
                        <li>OAUTH_SECRET_KEY=your_secret_key</li>
                    </ul>
                </body></html>
            """, status_code=500)
        
        return HTMLResponse(f"""
            <html><body>
                <h1>Alpaca MCP Server Authentication</h1>
                <p>Please authenticate with GitHub to access the Alpaca MCP Server.</p>
                <p>Only <strong>{oauth_manager.config.allowed_email}</strong> is authorized.</p>
                <a href="/auth/github" style="
                    background-color: #24292e; 
                    color: white; 
                    padding: 12px 20px; 
                    text-decoration: none; 
                    border-radius: 6px;
                    display: inline-block;
                    margin-top: 20px;
                ">Login with GitHub</a>
            </body></html>
        """)
    
    async def github_login(request: Request):
        """Initiate GitHub OAuth flow."""
        try:
            return await oauth_manager.get_login_url(request)
        except Exception as e:
            return JSONResponse({'error': str(e)}, status_code=500)
    
    async def auth_callback(request: Request):
        """Handle OAuth callback."""
        result = await oauth_manager.handle_callback(request)
        
        if result['success']:
            # Create session token
            token = oauth_manager.create_session_token(result['user_info'])
            
            # Set session
            request.session['auth_token'] = token
            request.session['user_info'] = result['user_info']
            
            return HTMLResponse(f"""
                <html><body>
                    <h1>Authentication Successful</h1>
                    <p>Welcome, {result['user_info']['name'] or result['user_info']['login']}!</p>
                    <p>You are now authenticated as {result['user_info']['email']}</p>
                    <p>You can now access the MCP server endpoints.</p>
                    <a href="/">Continue to MCP Server</a>
                </body></html>
            """)
        else:
            return HTMLResponse(f"""
                <html><body>
                    <h1>Authentication Failed</h1>
                    <p style="color: red;">{result['error']}</p>
                    <a href="/auth/login">Try Again</a>
                </body></html>
            """, status_code=401)
    
    async def logout(request: Request):
        """Logout user."""
        request.session.clear()
        return HTMLResponse("""
            <html><body>
                <h1>Logged Out</h1>
                <p>You have been successfully logged out.</p>
                <a href="/auth/login">Login Again</a>
            </body></html>
        """)
    
    return [
        Route('/auth/login', login_page),
        Route('/auth/github', github_login),
        Route('/auth/callback', auth_callback),
        Route('/auth/logout', logout),
    ]


def is_authenticated(request: Request, oauth_manager: OAuthManager) -> bool:
    """Check if request is authenticated."""
    if not oauth_manager.config.enabled:
        return True  # OAuth disabled, allow all requests
    
    # Check session
    auth_token = request.session.get('auth_token')
    if not auth_token:
        return False
    
    # Verify token
    user_info = oauth_manager.verify_session_token(auth_token)
    if not user_info:
        return False
    
    # Verify email still matches allowed email
    return user_info.get('email') == oauth_manager.config.allowed_email


async def auth_middleware(request: Request, call_next, oauth_manager: OAuthManager):
    """Authentication middleware."""
    # Skip auth for OAuth-related endpoints
    if request.url.path.startswith('/auth/'):
        response = await call_next(request)
        return response
    
    # Check authentication
    if not is_authenticated(request, oauth_manager):
        # Redirect to login page
        return RedirectResponse(url='/auth/login', status_code=302)
    
    response = await call_next(request)
    return response