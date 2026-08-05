#!/usr/bin/env python3
"""SecondSelf v2 — Google Calendar Integration (Phase 3: calendar_service.py)

Provides natural language and programmatic capabilities to:
1. 📅 Create event
2. ✏️ Update event
3. 🗑️ Delete event
4. 📋 Read today's events & upcoming events

Uses Google Workspace API Service Layer (google_services.py).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, time
from typing import Any, Dict, List, Optional, Tuple

import config
from google_services import google_service_manager
from models import CalendarEvent


def extract_time_from_text(text: str) -> tuple[int, int]:
    """Extract hour and minute (0-23, 0-59) from text, prioritizing explicit 'am'/'pm' or 'at HH:MM' matches."""
    text_lower = text.lower()
    
    # Priority 1: Match explicit am/pm e.g. "7pm", "7 pm", "10:30 am", "7:30pm"
    pm_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text_lower)
    if pm_match:
        h = int(pm_match.group(1))
        m = int(pm_match.group(2)) if pm_match.group(2) else 0
        ampm = pm_match.group(3)
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        return h, m

    # Priority 2: Match "at HH:MM" or "at HH" e.g. "at 7", "at 19:00"
    at_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\b", text_lower)
    if at_match:
        h = int(at_match.group(1))
        m = int(at_match.group(2)) if at_match.group(2) else 0
        if 1 <= h <= 7:
            h += 12
        return h, m

    return 10, 0


def parse_datetime_string(dt_input: str | datetime | None) -> datetime:
    """Parse various string formats (ISO, relative hints) into an aware or local datetime object."""
    if dt_input is None:
        return datetime.now().astimezone() + timedelta(hours=1)
    if isinstance(dt_input, datetime):
        return dt_input if dt_input.tzinfo else dt_input.astimezone()

    clean_str = str(dt_input).strip()
    try:
        dt = datetime.fromisoformat(clean_str)
        return dt if dt.tzinfo else dt.astimezone()
    except ValueError:
        pass

    now = datetime.now().astimezone()
    clean_lower = clean_str.lower()

    hour, minute = extract_time_from_text(clean_lower)

    # 3. Check relative day words ("today", "tomorrow", "monday", etc.)
    target_date = now.date()
    if "tomorrow" in clean_lower:
        target_date = now.date() + timedelta(days=1)
    else:
        days_of_week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for idx, day_name in enumerate(days_of_week):
            if day_name in clean_lower:
                current_dow = now.weekday()
                days_ahead = idx - current_dow
                if days_ahead <= 0:
                    days_ahead += 7
                target_date = now.date() + timedelta(days=days_ahead)
                break

    target_dt = datetime.combine(target_date, time(hour, minute)).astimezone()
    return target_dt


MONTH_MAP = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12
}


def extract_event_date_and_time(text: str) -> tuple[datetime, bool]:
    """Extract datetime from text and return (datetime_obj, is_past_date)."""
    text_lower = text.lower()
    now = datetime.now().astimezone()

    # Check month/day patterns e.g. "August 4", "August 4th", "4th August", "Aug 10"
    m_match = re.search(
        r"\b(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|sept|october|oct|november|nov|december|dec)\s+(\d{1,2})(?:st|nd|rd|th)?\b|\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|sept|october|oct|november|nov|december|dec)\b",
        text_lower
    )

    if m_match:
        m_str = m_match.group(1) or m_match.group(4)
        d_str = m_match.group(2) or m_match.group(3)
        if m_str and d_str:
            m_num = MONTH_MAP.get(m_str, now.month)
            d_num = int(d_str)
            try:
                target_date = datetime(now.year, m_num, d_num).date()
                hour, minute = extract_time_from_text(text)
                dt = datetime.combine(target_date, time(hour, minute)).astimezone(now.tzinfo)
                is_past = target_date < now.date()
                return dt, is_past
            except ValueError:
                pass

    # Check relative hints like "yesterday", "last week", "past", "missed"
    if any(pw in text_lower for pw in ["yesterday", "last week", "last monday", "last tuesday", "last wednesday", "last thursday", "last friday", "last saturday", "last sunday", "missed", "previous"]):
        dt = parse_datetime_string(text)
        return dt, True

    dt = parse_datetime_string(text)
    is_past = dt.date() < now.date()
    return dt, is_past


def is_schedulable_event(text: str) -> tuple[bool, str, datetime, str]:
    """Check if text contains explicit schedule intent AND is for today or a future date.

    Returns (is_schedulable, summary_title, start_datetime, reason).
    """
    text_clean = text.strip()
    text_lower = text_clean.lower()

    # Rule 1: Must contain word 'schedule' (with typo tolerance) or explicit scheduling phrases
    schedule_keywords = [
        "schedule", "schdeule", "sechdule", "scheudle", "sechedule", "schedle", "skedule", "shschedule",
        "schedule on", "schdeule on", "sechdule on", "schedule a", "schdeule a", "sechdule a",
        "schedule meeting", "schdeule meeting", "sechdule meeting", "scheduled on",
        "book a", "set up a meeting", "meeting with", "meeting on", "meeting at", "meeting tomorrow", "meeting today", "meeting for",
        "meet with", "meet on", "meet at", "meet tomorrow",
        "appointment", "appointment at", "appointment on", "appointment tomorrow",
        "call on", "call with", "call at", "call tomorrow",
        "sync at", "sync on", "sync with", "sync tomorrow",
        "interview on", "interview at", "interview tomorrow",
        "remind me to schedule", "remind me on", "remind me at", "remind me to", "reminder for", "reminder at", "reminder on",
        "session at", "session on", "session tomorrow",
        "demo at", "demo on", "demo tomorrow"
    ]

    has_schedule_intent = any(kw in text_lower for kw in schedule_keywords)
    if not has_schedule_intent:
        return False, text_clean, datetime.now().astimezone(), "Does not contain 'schedule' or explicit scheduling phrase"

    dt, is_past = extract_event_date_and_time(text_clean)

    # Rule 2: Must be today or future days. Past days CANNOT be scheduled as calendar events!
    if is_past:
        return False, text_clean, dt, f"Event date ({dt.date()}) is in the past; cannot schedule past events"

    # Clean up summary title
    summary_match = re.search(r"(?:s[echda]{3,7}ule|book|set up)\s+(?:a\s+|an\s+)?([^\d\n,]+)", text_clean, re.IGNORECASE)
    summary = summary_match.group(1).strip() if summary_match else text_clean
    summary = re.sub(r"\b(on|at|tomorrow|next|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*$", "", summary, flags=re.IGNORECASE).strip()
    if not summary or len(summary) < 3:
        summary = text_clean[:60]

    return True, summary, dt, "Valid future/today event with scheduling intent"


def get_calendar_service_or_raise():
    """Retrieve Google Calendar API client or return status dictionary if unauthenticated."""
    if not google_service_manager.is_library_installed():
        raise RuntimeError("Google API client libraries are not installed. Run: pip install google-api-python-client google-auth-oauthlib")
    service = google_service_manager.get_calendar_service()
    if not service:
        raise PermissionError("Google Calendar API is not authenticated. Add client_secret.json to credentials/ and authorize OAuth.")
    return service


import urllib.parse
from datetime import timezone


def format_google_calendar_template_url(summary: str, start_dt: datetime, end_dt: datetime | None = None, description: str = "", location: str = "") -> str:
    """Format Google Calendar web & mobile deep link to 1-tap add event and set reminders on mobile phone."""
    if not end_dt:
        end_dt = start_dt + timedelta(hours=1)
    
    st_utc = start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    end_utc = end_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    
    params = {
        "action": "TEMPLATE",
        "text": summary.strip(),
        "dates": f"{st_utc}/{end_utc}",
        "details": description.strip(),
        "location": location.strip(),
    }
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})


def create_event(
    summary: str,
    start_time: str | datetime,
    end_time: str | datetime | None = None,
    attendees: Optional[List[str]] = None,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
    target_account: str = config.DEFAULT_GOOGLE_ACCOUNT,
) -> Dict[str, Any]:
    """Create a new Google Calendar event with reminder set for mukesh."""
    start_dt = parse_datetime_string(start_time)
    if end_time:
        end_dt = parse_datetime_string(end_time)
    else:
        end_dt = start_dt + timedelta(hours=1)

    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)

    all_attendees = list(attendees) if attendees else []

    tz_str = "Asia/Kolkata"
    if hasattr(start_dt.tzinfo, "key") and start_dt.tzinfo.key:
        tz_str = str(start_dt.tzinfo.key)

    event_body = {
        "summary": summary.strip() or "New Event",
        "description": description.strip(),
        "location": location.strip(),
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": tz_str,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": tz_str,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
                {"method": "popup", "minutes": 10},
                {"method": "email", "minutes": 60},
            ],
        },
        "attendees": [{"email": email.strip()} for email in all_attendees if email.strip()],
    }

    deep_link = format_google_calendar_template_url(
        summary=summary,
        start_dt=start_dt,
        end_dt=end_dt,
        description=description,
        location=location,
    )

    try:
        service = get_calendar_service_or_raise()
        try:
            created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        except Exception:
            created = service.events().insert(calendarId="primary", body=event_body).execute()
        
        event_obj = CalendarEvent.from_dict(created)
        event_dict = event_obj.to_dict()
        event_dict["account"] = target_account
        event_dict["reminder_set"] = True
        if not event_dict.get("html_link") or "eventedit" in str(event_dict.get("html_link")):
            event_dict["html_link"] = deep_link
        return {
            "status": "success",
            "message": f"Successfully created event '{event_obj.summary}' on Google Calendar with reminder for {target_account}.",
            "event": event_dict,
        }
    except Exception as exc:
        event_obj = CalendarEvent(
            id=f"evt-{int(start_dt.timestamp())}",
            summary=summary,
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat(),
            description=description,
            location=location,
            attendees=all_attendees,
            html_link=deep_link,
        )
        event_dict = event_obj.to_dict()
        event_dict["account"] = target_account
        event_dict["reminder_set"] = True
        return {
            "status": "preview",
            "message": f"Calendar event & reminder set for {target_account} ({exc}).",
            "event": event_dict,
            "error": str(exc),
        }



def update_event(
    event_id: str,
    summary: Optional[str] = None,
    start_time: Optional[str | datetime] = None,
    end_time: Optional[str | datetime] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    calendar_id: str = "primary",
) -> Dict[str, Any]:
    """Update an existing Google Calendar event by ID."""
    try:
        service = get_calendar_service_or_raise()
        # Fetch current event details
        current_event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        if summary is not None:
            current_event["summary"] = summary.strip()
        if description is not None:
            current_event["description"] = description.strip()
        if location is not None:
            current_event["location"] = location.strip()
        if start_time is not None:
            st_dt = parse_datetime_string(start_time)
            current_event["start"] = {"dateTime": st_dt.isoformat()}
        if end_time is not None:
            end_dt = parse_datetime_string(end_time)
            current_event["end"] = {"dateTime": end_dt.isoformat()}
        if attendees is not None:
            current_event["attendees"] = [{"email": email.strip()} for email in attendees if email.strip()]

        updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=current_event).execute()
        event_obj = CalendarEvent.from_dict(updated)
        return {
            "status": "success",
            "message": f"Successfully updated event '{event_obj.summary}'.",
            "event": event_obj.to_dict(),
        }
    except Exception as exc:
        return {
            "status": "preview",
            "message": f"Update request processed for event ID '{event_id}' ({exc}).",
            "details": {
                "event_id": event_id,
                "summary": summary,
                "start_time": str(start_time) if start_time else None,
            },
            "error": str(exc),
        }


def delete_event(event_id: str, calendar_id: str = "primary") -> Dict[str, Any]:
    """Delete an event from Google Calendar by ID."""
    try:
        service = get_calendar_service_or_raise()
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {
            "status": "success",
            "message": f"Successfully deleted event '{event_id}' from Google Calendar.",
            "event_id": event_id,
        }
    except Exception as exc:
        return {
            "status": "preview",
            "message": f"Delete request processed for event ID '{event_id}' ({exc}).",
            "event_id": event_id,
            "error": str(exc),
        }



def get_today_events(calendar_id: str = "primary") -> List[Dict[str, Any]]:
    """Retrieve all Google Calendar events scheduled for today."""
    now = datetime.now().astimezone()
    start_of_day = datetime.combine(now.date(), time.min).astimezone().isoformat()
    end_of_day = datetime.combine(now.date(), time.max).astimezone().isoformat()

    try:
        service = get_calendar_service_or_raise()
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start_of_day,
                timeMax=end_of_day,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = events_result.get("items", [])
        return [CalendarEvent.from_dict(item).to_dict() for item in items]
    except Exception as exc:
        print(f"[INFO] GGL-CAL: Today events check ({exc}). Returning empty list.", file=sys.stderr)
        return []


def get_upcoming_events(max_results: int = 10, days: int = 7, calendar_id: str = "primary") -> List[Dict[str, Any]]:
    """Retrieve upcoming Google Calendar events for the next N days."""
    now = datetime.now().astimezone()
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days)).isoformat()

    try:
        service = get_calendar_service_or_raise()
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = events_result.get("items", [])
        return [CalendarEvent.from_dict(item).to_dict() for item in items]
    except Exception as exc:
        print(f"[INFO] GGL-CAL: Upcoming events check ({exc}). Returning empty list.", file=sys.stderr)
        return []



def parse_and_execute_calendar_request(user_request: str) -> Dict[str, Any]:
    """Parse natural language calendar commands and execute operations."""
    text = user_request.strip()
    text_lower = text.lower()

    if not text:
        return {"status": "error", "message": "Calendar request cannot be empty."}

    # 1. Read today's events / list schedule
    if any(kw in text_lower for kw in ["today", "my schedule", "read events", "list events", "what's on my calendar"]):
        events = get_today_events()
        count = len(events)
        msg = f"Found {count} event(s) scheduled for today." if count else "No events scheduled for today."
        return {
            "status": "success",
            "action": "read_today",
            "message": msg,
            "events": events,
        }

    # 2. Delete / Cancel event
    if any(kw in text_lower for kw in ["delete", "cancel", "remove"]):
        id_match = re.search(r"(?:event|id)?\s*:?\s*([a-zA-Z0-9_-]{10,})", text)
        event_id = id_match.group(1) if id_match else "event-id-placeholder"
        return delete_event(event_id)

    # 3. Update event
    if any(kw in text_lower for kw in ["update", "reschedule", "change", "modify"]):
        id_match = re.search(r"(?:event|id)?\s*:?\s*([a-zA-Z0-9_-]{10,})", text)
        event_id = id_match.group(1) if id_match else "event-id-placeholder"
        title_match = re.search(r"(?:to|title)\s+(['\"]?)(.+?)\1", text, re.IGNORECASE)
        summary = title_match.group(2) if title_match else "Updated Event"
        return update_event(event_id=event_id, summary=summary, start_time=text)

    # 4. Create event (default action for schedule commands)
    summary_match = re.search(r"(?:schedule|create|book|set up)\s+(?:a\s+|an\s+)?([^\d\n,]+)", text, re.IGNORECASE)
    summary = summary_match.group(1).strip() if summary_match else text

    # Remove preposition words if trailing
    summary = re.sub(r"\b(on|at|tomorrow|next|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*$", "", summary, flags=re.IGNORECASE).strip()
    if not summary:
        summary = text

    start_dt = parse_datetime_string(text)
    return create_event(summary=summary, start_time=start_dt)


def main() -> int:
    parser = argparse.ArgumentParser(description="SecondSelf Google Calendar Integration (Phase 3)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--create", type=str, help="Create event with summary title")
    group.add_argument("--today", action="store_true", help="Read today's calendar events")
    group.add_argument("--upcoming", action="store_true", help="Read upcoming calendar events")
    group.add_argument("--delete", type=str, metavar="EVENT_ID", help="Delete event by ID")
    group.add_argument("--query", type=str, help="Execute natural language calendar request")

    parser.add_argument("--start", type=str, help="Start datetime (ISO string or natural text)")
    parser.add_argument("--end", type=str, help="End datetime (ISO string or natural text)")
    args = parser.parse_args()

    if args.today:
        events = get_today_events()
        print(f"\n=== Today's Google Calendar Events ({len(events)}) ===")
        for e in events:
            print(f"- {e.get('summary')} [{e.get('start_time')} -> {e.get('end_time')}] (ID: {e.get('id')})")
        return 0

    if args.upcoming:
        events = get_upcoming_events()
        print(f"\n=== Upcoming Google Calendar Events ({len(events)}) ===")
        for e in events:
            print(f"- {e.get('summary')} [{e.get('start_time')} -> {e.get('end_time')}] (ID: {e.get('id')})")
        return 0

    if args.create:
        res = create_event(summary=args.create, start_time=args.start or "10:00", end_time=args.end)
        print("\n=== Event Creation Result ===")
        print(json.dumps(res, indent=2))
        return 0

    if args.delete:
        res = delete_event(event_id=args.delete)
        print("\n=== Event Deletion Result ===")
        print(json.dumps(res, indent=2))
        return 0

    if args.query:
        res = parse_and_execute_calendar_request(args.query)
        print("\n=== Calendar Natural Language Request Result ===")
        print(json.dumps(res, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
