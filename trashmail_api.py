"""
TrashMail API Client for Python

This module provides authentication and API access to TrashMail.com.

IMPORTANT: Library Compatibility Issue
======================================
TrashMail uses @serenity-kit/opaque (JavaScript/WASM, based on Facebook's opaque-ke Rust library).
The Python `opaque` package (libopaque) is a DIFFERENT implementation and is NOT compatible!

Key differences:
- @serenity-kit/opaque: Uses opaque-ke (Rust), Argon2id key stretching, specific serialization
- libopaque (Python): Uses libsodium, different internal structure, incompatible wire format

Solutions provided here:
1. Classic Login (recommended) - Works immediately, simple, reliable
2. WASM-based OPAQUE (advanced) - Requires loading the JS WASM module in Python

For most API automation use cases, the classic login is sufficient and recommended.

Author: TrashMail Team (Aionda GmbH)
"""

import base64
import logging
import os
import time
from typing import Optional, Tuple, Dict, Any

import requests
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError

# Configuration
API_BASE_URL = os.getenv("TRASHMAIL_API_URL", "https://trashmail.com").rstrip("/")
DEFAULT_LANG = os.getenv("TRASHMAIL_LANG", "en")[:2]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TrashMailAPIError(Exception):
    """Exception raised for TrashMail API errors."""

    def __init__(self, message: str, error_code: Optional[int] = None, response: Optional[requests.Response] = None):
        super().__init__(message)
        self.error_code = error_code
        self.response = response


class TrashMailClient:
    """
    TrashMail API Client

    Provides authentication and API access to TrashMail.com.

    Usage:
        client = TrashMailClient()

        # Login with username/password
        if client.login("user@example.com", "password"):
            # Make authenticated API calls
            deas = client.api_call("read_dea")
            print(deas)
    """

    def __init__(self, base_url: str = API_BASE_URL, lang: str = DEFAULT_LANG):
        self.base_url = base_url
        self.lang = lang
        self.session = requests.Session()
        self._authenticated = False
        self._username: Optional[str] = None

    def _build_url(self, cmd: str, api: bool = True, **extra_params) -> Dict[str, Any]:
        """Build API URL with parameters."""
        params = {"lang": self.lang}
        if api:
            params["api"] = 1
        if cmd:
            params["cmd"] = cmd
        params.update(extra_params)
        return {"url": f"{self.base_url}/", "params": params}

    def _safe_json(self, response: requests.Response) -> Optional[Dict]:
        """Safely parse JSON response."""
        try:
            return response.json()
        except RequestsJSONDecodeError:
            logger.exception("Failed to decode JSON response")
            return None

    def check_auth_methods(self, username: str) -> Dict[str, bool]:
        """
        Check which authentication methods are available for a user.

        Returns:
            Dict with keys: opaque_enabled, srp_enabled, migration_available
        """
        try:
            response = self.session.post(
                **self._build_url("opaque_check"),
                json={"username": username}
            )
            result = self._safe_json(response) or {}
            return {
                "opaque_enabled": result.get("opaque_enabled", False),
                "srp_enabled": result.get("srp_enabled", False),
                "migration_available": result.get("migration_available", False),
            }
        except Exception:
            logger.exception("Auth method check failed for %s", username)
            return {"opaque_enabled": False, "srp_enabled": False, "migration_available": False}

    def login(self, username: str, password: str) -> bool:
        """
        Login to TrashMail using the classic authentication method.

        This is the recommended approach for API automation.
        The server will automatically migrate the account to OPAQUE after login.

        Args:
            username: TrashMail username (email)
            password: Account password

        Returns:
            True if login successful, False otherwise

        Raises:
            TrashMailAPIError: If login fails with specific error
        """
        try:
            response = self.session.post(
                **self._build_url("login"),
                json={
                    "fe-login-user": username,
                    "fe-login-pass": password
                }
            )

            result = self._safe_json(response)
            if not result:
                raise TrashMailAPIError("Invalid response from server")

            if result.get("success"):
                self._authenticated = True
                self._username = username
                logger.info("Login successful for %s", username)

                # Check if 2FA is required
                data = result.get("data", {})
                if data.get("requires_2fa"):
                    logger.warning("2FA required - not yet implemented in this client")
                    return False

                return True
            else:
                error_msg = result.get("msg", "Login failed")
                error_code = result.get("error_code")
                raise TrashMailAPIError(error_msg, error_code, response)

        except TrashMailAPIError:
            raise
        except Exception as e:
            logger.exception("Login failed for %s", username)
            raise TrashMailAPIError(f"Login error: {e}")

    def login_with_pat(self, username: str, pat_token: str) -> bool:
        """
        Login using a Personal Access Token (PAT).

        NOTE: PAT authentication uses OPAQUE protocol on the server side.
        This implementation uses the classic login fallback which accepts PATs.

        For full OPAQUE PAT authentication, you would need to:
        1. Load the @serenity-kit/opaque WASM module
        2. Implement the OPAQUE protocol in Python

        Args:
            username: TrashMail username
            pat_token: Personal Access Token (starts with 'tmpat_')

        Returns:
            True if login successful
        """
        if not pat_token.startswith("tmpat_"):
            raise ValueError("Invalid PAT format. Must start with 'tmpat_'")

        # Try classic login with PAT as password
        # This may work depending on server configuration
        return self.login(username, pat_token)

    def api_call(self, cmd: str, **params) -> Dict:
        """
        Make an authenticated API call.

        Args:
            cmd: API command name
            **params: Additional parameters for the API call

        Returns:
            API response as dictionary

        Raises:
            TrashMailAPIError: If not authenticated or API call fails
        """
        if not self._authenticated:
            raise TrashMailAPIError("Not authenticated. Call login() first.")

        response = self.session.post(
            **self._build_url(cmd),
            json=params
        )

        result = self._safe_json(response)
        if not result:
            raise TrashMailAPIError("Invalid response from server")

        if not result.get("success", True):  # Some endpoints don't return success
            error_msg = result.get("msg", "API call failed")
            error_code = result.get("error_code")
            raise TrashMailAPIError(error_msg, error_code, response)

        return result

    def get_deas(self) -> list:
        """Get list of Disposable Email Addresses (DEAs)."""
        result = self.api_call("read_dea")
        return result.get("data", [])

    def create_dea(self, real_email: str, **options) -> Dict:
        """
        Create a new Disposable Email Address.

        Args:
            real_email: The real email address to forward to
            **options: Additional options (expire, forwards, etc.)

        Returns:
            The created DEA data
        """
        params = {"realemail": real_email}
        params.update(options)
        result = self.api_call("save_dea", **params)
        return result.get("data", {})

    def logout(self) -> bool:
        """Logout and clear session."""
        try:
            self.api_call("logout")
        except Exception:
            pass  # Logout errors are not critical

        self._authenticated = False
        self._username = None
        self.session = requests.Session()
        return True

    @property
    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._authenticated

    @property
    def username(self) -> Optional[str]:
        """Get current username if authenticated."""
        return self._username


# =============================================================================
# OPAQUE Implementation Notes
# =============================================================================
#
# The code below is kept for reference but WILL NOT WORK because libopaque
# is not compatible with @serenity-kit/opaque.
#
# If you need true OPAQUE authentication in Python, you have these options:
#
# Option 1: Use wasmer/wasmtime to load the @serenity-kit/opaque WASM module
# ---------------------------------------------------------------------------
# This is complex but would give you full compatibility:
#
#   import wasmer
#   wasm_bytes = open("opaque.wasm", "rb").read()
#   store = wasmer.Store()
#   module = wasmer.Module(store, wasm_bytes)
#   instance = wasmer.Instance(module)
#   # Call OPAQUE functions through WASM interface
#
# Option 2: Use a subprocess to call Node.js
# -------------------------------------------
# If you have Node.js installed:
#
#   import subprocess
#   result = subprocess.run(
#       ["node", "-e", "require('@serenity-kit/opaque').client.startLogin(...)"],
#       capture_output=True
#   )
#
# Option 3: Create Python bindings for opaque-ke (Rust)
# ------------------------------------------------------
# Using PyO3, you could create Python bindings for the Rust opaque-ke library.
# This would require Rust toolchain and compilation.
#
# For most use cases, the classic login method above is sufficient and recommended.
# =============================================================================


def is_pat_token(password: str) -> bool:
    """Check if a password is a Personal Access Token."""
    return bool(password and isinstance(password, str) and password.startswith("tmpat_") and len(password) > 6)


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    import sys

    # Example: Login and list DEAs
    username = os.getenv("TRASHMAIL_USER", "")
    password = os.getenv("TRASHMAIL_PASS", "")

    if not username or not password:
        print("Set TRASHMAIL_USER and TRASHMAIL_PASS environment variables")
        print("Example:")
        print("  export TRASHMAIL_USER='your@email.com'")
        print("  export TRASHMAIL_PASS='your_password'")
        sys.exit(1)

    client = TrashMailClient()

    try:
        # Check available auth methods
        auth_methods = client.check_auth_methods(username)
        print(f"Auth methods for {username}: {auth_methods}")

        # Login
        if client.login(username, password):
            print(f"Logged in as: {client.username}")

            # Get DEAs
            deas = client.get_deas()
            print(f"Found {len(deas)} DEAs")
            for dea in deas[:5]:  # Show first 5
                print(f"  - {dea.get('dea', 'unknown')}")

            # Logout
            client.logout()
            print("Logged out successfully")
        else:
            print("Login failed")
            sys.exit(1)

    except TrashMailAPIError as e:
        print(f"API Error: {e} (code: {e.error_code})")
        sys.exit(1)
