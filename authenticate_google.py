#!/usr/bin/env python3
"""SecondSelf Google Workspace OAuth Authorizer.

Runs the local OAuth authentication server so you can log into your Google account
and grant calendar permissions. Generates credentials/token.json.
"""

import sys
import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

import config
from google_services import google_service_manager

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def main():
    print("==================================================")
    print("  SecondSelf Google Workspace OAuth Authorizer    ")
    print("==================================================")
    
    if not google_service_manager.has_client_secrets():
        print("[ERROR] client_secret.json not found in credentials/ folder.")
        sys.exit(1)

    print("\n[INFO] Starting Google OAuth authorization flow on http://localhost:8080/ ...")
    print("Opening browser window for Google sign-in...")
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(config.GOOGLE_CLIENT_SECRET_FILE),
            scopes=config.GOOGLE_SCOPES
        )
        
        # Fixed port 8080 matching Google Cloud Console Authorized redirect URI
        creds = flow.run_local_server(host="localhost", port=8080, open_browser=True, prompt="consent")
        
        # Save token
        token_path = config.GOOGLE_TOKEN_FILE
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        
        print("\n[SUCCESS] Google Workspace OAuth Authentication successful!")
        print(f"Token saved to: {token_path}")
        print("Your Google Calendar events & reminders will now automatically sync to your mobile phone and Google account!")

    except Exception as exc:
        print(f"\n[ERROR] OAuth authorization error: {exc}")
        print("\nNOTE: If you see 'redirect_uri_mismatch' in browser:")
        print("  1. Go to Google Cloud Console -> Credentials")
        print("  2. Click on your OAuth Client ID")
        print("  3. Under 'Authorized redirect URIs', add: http://localhost:8080/")
        print("  4. Click Save and try again.")


if __name__ == "__main__":
    main()
