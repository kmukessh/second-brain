#!/usr/bin/env python3
"""SecondSelf v2 — Google Workspace API Service Layer (Phase 0)

Provides a unified, reusable authentication and service builder layer for:
1. 📅 Google Calendar API (v3)
2. 📧 Gmail API (v1)
3. 📝 Google Tasks API (v1)

Handles OAuth2 token caching in credentials/token.json and user authentication flows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import config

# Lazy imports for Google API libraries
_GOOGLE_CLIENT_AVAILABLE = True
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import Resource, build
except ImportError:
    _GOOGLE_CLIENT_AVAILABLE = False


class GoogleServiceManager:
    """Reusable Google Workspace OAuth2 and API Client Manager."""

    def __init__(
        self,
        client_secret_file: Path = config.GOOGLE_CLIENT_SECRET_FILE,
        token_file: Path = config.GOOGLE_TOKEN_FILE,
        scopes: list[str] = config.GOOGLE_SCOPES,
    ):
        self.client_secret_file = client_secret_file
        self.token_file = token_file
        self.scopes = scopes
        self._credentials: Optional[Credentials] = None
        self._calendar_service: Optional[Any] = None
        self._gmail_service: Optional[Any] = None
        self._tasks_service: Optional[Any] = None

    def is_library_installed(self) -> bool:
        """Check if Google API Python client libraries are installed."""
        return _GOOGLE_CLIENT_AVAILABLE

    def has_client_secrets(self) -> bool:
        """Check if credentials/client_secret.json exists."""
        return self.client_secret_file.exists() and self.client_secret_file.stat().st_size > 0

    def is_authenticated(self) -> bool:
        """Check if valid OAuth2 credentials exist."""
        creds = self.get_credentials()
        return creds is not None and creds.valid

    def get_credentials(self) -> Optional[Credentials]:
        """Retrieve, refresh, or authenticate OAuth2 user credentials."""
        if not self.is_library_installed():
            return None

        if self._credentials and self._credentials.valid:
            return self._credentials

        creds = None
        # Load token if it exists
        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_file), self.scopes)
            except Exception as exc:
                print(f"[WARNING] GGL-01: Invalid token file '{self.token_file.name}': {exc}")

        # Refresh expired token if possible
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                print(f"[WARNING] GGL-02: Could not refresh token: {exc}")
                creds = None

        # Authenticate if missing or invalid
        if not creds or not creds.valid:
            if self.has_client_secrets():
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret_file), self.scopes)
                    creds = flow.run_local_server(port=0)
                    # Persist token for future runs
                    self.token_file.parent.mkdir(parents=True, exist_ok=True)
                    self.token_file.write_text(creds.to_json(), encoding="utf-8")
                except Exception as exc:
                    print(f"[ERROR] GGL-03: OAuth authentication flow failed: {exc}")
                    return None
            else:
                return None

        self._credentials = creds
        return creds

    def get_calendar_service(self) -> Optional[Any]:
        """Build and return Google Calendar API (v3) client."""
        if self._calendar_service:
            return self._calendar_service
        creds = self.get_credentials()
        if not creds:
            return None
        try:
            self._calendar_service = build("calendar", "v3", credentials=creds)
            return self._calendar_service
        except Exception as exc:
            print(f"[ERROR] GGL-04: Failed to build Calendar service: {exc}")
            return None

    def get_gmail_service(self) -> Optional[Any]:
        """Build and return Gmail API (v1) client."""
        if self._gmail_service:
            return self._gmail_service
        creds = self.get_credentials()
        if not creds:
            return None
        try:
            self._gmail_service = build("gmail", "v1", credentials=creds)
            return self._gmail_service
        except Exception as exc:
            print(f"[ERROR] GGL-05: Failed to build Gmail service: {exc}")
            return None

    def get_tasks_service(self) -> Optional[Any]:
        """Build and return Google Tasks API (v1) client."""
        if self._tasks_service:
            return self._tasks_service
        creds = self.get_credentials()
        if not creds:
            return None
        try:
            self._tasks_service = build("tasks", "v1", credentials=creds)
            return self._tasks_service
        except Exception as exc:
            print(f"[ERROR] GGL-06: Failed to build Tasks service: {exc}")
            return None

    def get_status_summary(self) -> Dict[str, Any]:
        """Get diagnostic status summary for UI dashboard and setup checks."""
        return {
            "library_installed": self.is_library_installed(),
            "client_secrets_found": self.has_client_secrets(),
            "authenticated": self.is_authenticated(),
            "client_secret_path": str(self.client_secret_file.relative_to(config.ROOT)),
            "token_path": str(self.token_file.relative_to(config.ROOT)),
            "scopes": self.scopes,
        }


# Singleton instance for application-wide use
google_service_manager = GoogleServiceManager()


if __name__ == "__main__":
    status = google_service_manager.get_status_summary()
    print("=== SecondSelf v2 — Google Service Layer Status ===")
    print(json.dumps(status, indent=2))
