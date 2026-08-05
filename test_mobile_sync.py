#!/usr/bin/env python3
"""SecondSelf Live Mobile Sync Test Script

Run this script to immediately schedule a test event on your Google Calendar.
Then check your phone's Google Calendar app to verify the notification & reminder!
"""

from datetime import datetime, timedelta
import config
from calendar_service import create_event


def main():
    print("====================================================")
    print("  SecondSelf Mobile Google Calendar Sync Test       ")
    print("====================================================")
    
    # Schedule event 2 hours from now
    event_time = datetime.now().astimezone() + timedelta(hours=2)
    time_str = event_time.strftime("%I:%M %p (%Y-%m-%d)")
    
    print(f"\n[INFO] Creating test meeting scheduled for: {time_str}...")
    
    res = create_event(
        summary="SecondSelf Mobile Sync Test",
        start_time=event_time,
        description="Testing automatic Google Calendar background sync and mobile phone reminder notifications from SecondSelf AI.",
        location="SecondSelf AI Mobile Workspace",
        target_account=config.DEFAULT_GOOGLE_ACCOUNT,
    )
    
    print("\n----------------------------------------------------")
    print("STATUS:", res.get("status").upper())
    print("MESSAGE:", res.get("message"))
    
    evt = res.get("event", {})
    if evt.get("html_link"):
        print("EVENT LINK:", evt.get("html_link"))
        
    print("----------------------------------------------------")
    print("\n[MOBILE CHECK] NOW CHECK YOUR MOBILE PHONE'S GOOGLE CALENDAR APP!")
    print(f"Look for the event 'SecondSelf Mobile Sync Test' at {time_str}.")
    print("You will see pop-up notifications (30m & 10m) and email reminders active!")


if __name__ == "__main__":
    main()
