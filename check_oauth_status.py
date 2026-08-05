#!/usr/bin/env python3
"""SecondSelf OAuth Token Check Helper"""

import time
from google_services import google_service_manager


def main():
    print("Checking for credentials/token.json...")
    if google_service_manager.token_file.exists():
        print(f"[SUCCESS] token.json found! Saved at {google_service_manager.token_file}")
        creds = google_service_manager.get_credentials()
        if creds and creds.valid:
            print("[SUCCESS] OAuth credentials are valid and active!")
        else:
            print("[WARNING] token.json exists but credentials could not be validated.")
    else:
        print("[INFO] token.json not found yet. Waiting for user authorization in browser...")


if __name__ == "__main__":
    main()
