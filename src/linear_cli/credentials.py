"""
Standalone credential storage for Linear CLI.

No external dependencies - works with:
- Environment variables (LINEAR_*)
- OS Keyring (if 'keyring' package installed)
- .env file fallback

Compatible with Forma workspaces but doesn't require forma-cli.
"""

import os
from pathlib import Path

try:
    import keyring
    from keyring.errors import KeyringError

    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    KeyringError = Exception  # type: ignore


class CredentialStore:
    """Credential storage with env -> keyring -> .env priority."""

    SERVICE = "linear"
    KEYRING_SERVICE = f"forma-{SERVICE}"

    def __init__(self, env_file: Path | None = None):
        self.env_file = env_file or Path.cwd() / ".env"

    def _env_var(self, key: str) -> str:
        """Convert key to env var name: api_key -> LINEAR_API_KEY"""
        return f"{self.SERVICE.upper()}_{key.upper()}"

    def get(self, key: str) -> str | None:
        """Get credential: env -> keyring -> .env"""
        if value := os.environ.get(self._env_var(key)):
            return value

        if KEYRING_AVAILABLE:
            try:
                if value := keyring.get_password(self.KEYRING_SERVICE, key):
                    return value
            except KeyringError:
                pass

        return self._get_from_dotenv(key)

    def set(self, key: str, value: str) -> None:
        """Store credential in keyring, or .env if unavailable."""
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(self.KEYRING_SERVICE, key, value)
                return
            except KeyringError:
                pass

        self._set_in_dotenv(key, value)

    def delete(self, key: str) -> bool:
        """Delete credential from keyring and .env."""
        deleted = False

        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password(self.KEYRING_SERVICE, key)
                deleted = True
            except KeyringError:
                pass

        if self._delete_from_dotenv(key):
            deleted = True

        return deleted

    def get_source(self, key: str) -> str:
        """Identify where credential is stored: environment|keyring|dotenv|none"""
        if os.environ.get(self._env_var(key)):
            return "environment"

        if KEYRING_AVAILABLE:
            try:
                if keyring.get_password(self.KEYRING_SERVICE, key):
                    return "keyring"
            except KeyringError:
                pass

        if self._get_from_dotenv(key):
            return "dotenv"

        return "none"

    def status(self) -> dict:
        """Get authentication status."""
        source = self.get_source("api_key")
        return {
            "authenticated": source != "none",
            "source": source,
            "keyring_available": KEYRING_AVAILABLE,
        }

    def _parse_dotenv(self) -> dict[str, str]:
        """Parse .env file into dict."""
        if not self.env_file.exists():
            return {}

        result = {}
        try:
            for line in self.env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip().strip("\"'")
                    result[key.strip()] = value
        except OSError:
            pass

        return result

    def _write_dotenv(self, data: dict[str, str]) -> None:
        """Write dict to .env file."""
        lines = [f"{k}={v}" for k, v in sorted(data.items())]
        try:
            self.env_file.parent.mkdir(parents=True, exist_ok=True)
            self.env_file.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
            if os.name != "nt":
                os.chmod(self.env_file, 0o600)
        except OSError:
            pass

    def _get_from_dotenv(self, key: str) -> str | None:
        return self._parse_dotenv().get(self._env_var(key))

    def _set_in_dotenv(self, key: str, value: str) -> None:
        data = self._parse_dotenv()
        data[self._env_var(key)] = value
        self._write_dotenv(data)

    def _delete_from_dotenv(self, key: str) -> bool:
        data = self._parse_dotenv()
        env_key = self._env_var(key)
        if env_key in data:
            del data[env_key]
            self._write_dotenv(data)
            return True
        return False


_store: CredentialStore | None = None


def get_credential_store() -> CredentialStore:
    """Get or create the credential store singleton."""
    global _store
    if _store is None:
        _store = CredentialStore()
    return _store
