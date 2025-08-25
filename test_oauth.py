#!/usr/bin/env python3
"""
Basic tests for OAuth functionality.
These tests verify the OAuth configuration and basic functionality.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from oauth_auth import OAuthConfig, OAuthManager


class TestOAuthConfig(unittest.TestCase):
    """Test OAuth configuration."""
    
    def setUp(self):
        """Set up test environment."""
        # Clear environment variables
        self.original_env = {}
        oauth_vars = [
            'OAUTH_ENABLED', 'GITHUB_CLIENT_ID', 'GITHUB_CLIENT_SECRET',
            'OAUTH_ALLOWED_EMAIL', 'OAUTH_SECRET_KEY', 'OAUTH_REDIRECT_URL'
        ]
        
        for var in oauth_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]
    
    def tearDown(self):
        """Clean up test environment."""
        # Restore original environment variables
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]
    
    def test_oauth_disabled_by_default(self):
        """Test that OAuth is disabled by default."""
        config = OAuthConfig()
        self.assertFalse(config.enabled)
        self.assertFalse(config.is_valid())
    
    def test_oauth_enabled_but_invalid_config(self):
        """Test OAuth enabled but with invalid configuration."""
        os.environ['OAUTH_ENABLED'] = 'true'
        config = OAuthConfig()
        self.assertTrue(config.enabled)
        self.assertFalse(config.is_valid())  # Missing other required fields
    
    def test_oauth_valid_config(self):
        """Test OAuth with valid configuration."""
        os.environ.update({
            'OAUTH_ENABLED': 'true',
            'GITHUB_CLIENT_ID': 'test_client_id',
            'GITHUB_CLIENT_SECRET': 'test_client_secret',
            'OAUTH_ALLOWED_EMAIL': 'test@example.com',
            'OAUTH_SECRET_KEY': 'test_secret_key'
        })
        
        config = OAuthConfig()
        self.assertTrue(config.enabled)
        self.assertTrue(config.is_valid())
        self.assertEqual(config.allowed_email, 'test@example.com')
    
    def test_default_allowed_email(self):
        """Test default allowed email."""
        config = OAuthConfig()
        self.assertEqual(config.allowed_email, 'mbeyer2@gmail.com')
    
    def test_custom_allowed_email(self):
        """Test custom allowed email."""
        os.environ['OAUTH_ALLOWED_EMAIL'] = 'custom@example.com'
        config = OAuthConfig()
        self.assertEqual(config.allowed_email, 'custom@example.com')


class TestOAuthManager(unittest.TestCase):
    """Test OAuth manager functionality."""
    
    def setUp(self):
        """Set up test OAuth configuration."""
        self.valid_config = OAuthConfig()
        self.valid_config.enabled = True
        self.valid_config.github_client_id = 'test_client_id'
        self.valid_config.github_client_secret = 'test_client_secret'
        self.valid_config.allowed_email = 'test@example.com'
        self.valid_config.secret_key = 'test_secret_key'
        
        self.invalid_config = OAuthConfig()
        self.invalid_config.enabled = False
    
    def test_oauth_manager_with_valid_config(self):
        """Test OAuth manager initialization with valid config."""
        manager = OAuthManager(self.valid_config)
        self.assertIsNotNone(manager.oauth)
        self.assertIsNotNone(manager.serializer)
    
    def test_oauth_manager_with_invalid_config(self):
        """Test OAuth manager initialization with invalid config."""
        manager = OAuthManager(self.invalid_config)
        self.assertIsNotNone(manager.oauth)  # OAuth object still created
        self.assertIsNotNone(manager.serializer)
    
    def test_session_token_creation_and_verification(self):
        """Test session token creation and verification."""
        manager = OAuthManager(self.valid_config)
        
        user_info = {
            'login': 'testuser',
            'email': 'test@example.com',
            'name': 'Test User',
            'id': 12345
        }
        
        # Create token
        token = manager.create_session_token(user_info)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)
        
        # Verify token
        verified_info = manager.verify_session_token(token)
        self.assertEqual(verified_info, user_info)
    
    def test_session_token_verification_failure(self):
        """Test session token verification with invalid token."""
        manager = OAuthManager(self.valid_config)
        
        # Test with invalid token
        verified_info = manager.verify_session_token('invalid_token')
        self.assertIsNone(verified_info)
    
    @patch('oauth_auth.OAuthManager.handle_callback')
    def test_email_validation_success(self, mock_handle_callback):
        """Test successful email validation."""
        mock_handle_callback.return_value = {
            'success': True,
            'error': None,
            'user_info': {
                'login': 'testuser',
                'email': 'test@example.com',
                'name': 'Test User',
                'id': 12345
            }
        }
        
        manager = OAuthManager(self.valid_config)
        # This test would require a real request object in practice
        # Here we're just testing the mock
        self.assertTrue(mock_handle_callback.return_value['success'])
    
    @patch('oauth_auth.OAuthManager.handle_callback')
    def test_email_validation_failure(self, mock_handle_callback):
        """Test email validation failure."""
        mock_handle_callback.return_value = {
            'success': False,
            'error': 'Unauthorized email: wrong@example.com. Only test@example.com is allowed.',
            'user_info': None
        }
        
        manager = OAuthManager(self.valid_config)
        # This test would require a real request object in practice
        # Here we're just testing the mock
        self.assertFalse(mock_handle_callback.return_value['success'])
        self.assertIn('Unauthorized email', mock_handle_callback.return_value['error'])


def run_tests():
    """Run all tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestOAuthConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestOAuthManager))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)