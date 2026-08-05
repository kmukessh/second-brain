#!/usr/bin/env python3
"""SecondSelf Google OAuth Setup - Desktop App Flow"""

import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
import config

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def run_oauth():
    print("=====================================================")
    print("  SecondSelf Google Calendar Automatic Reminder Setup")
    print("=====================================================")
    
    client_secret_file = config.GOOGLE_CLIENT_SECRET_FILE
    if not client_secret_file.exists():
        print("[ERROR] client_secret.json not found in credentials/ folder.")
        sys.exit(1)

    print("\n[STEP 1] Initializing OAuth Flow with Desktop Credentials...")
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret_file),
        scopes=config.GOOGLE_SCOPES,
        redirect_uri="http://localhost:8080/"
    )
    
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    
    print("\n[STEP 2] Click or open this authorization URL:")
    print(f"\n{auth_url}\n")
    print("Waiting for sign-in in browser...")
    
    try:
        creds = flow.run_local_server(host="localhost", port=8080, open_browser=True, prompt="consent")
        
        token_path = config.GOOGLE_TOKEN_FILE
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        
        print("\n=====================================================")
        print(" [SUCCESS] GOOGLE CALENDAR AUTOMATIC SYNC ENABLED! ")
        print("=====================================================")
        print(f"Token saved to: {token_path}")
        print("Now every scheduled meeting captured in SecondSelf will AUTOMATICALLY create reminders directly on your Google Calendar without clicking any links!")
    except Exception as exc:
        print(f"\n[ERROR] Authorization failed: {exc}")


if __name__ == "__main__":
    run_oauth()
