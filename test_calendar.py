#!/usr/bin/env python3
"""Unit tests for Phase 3 Google Calendar Integration (test_calendar.py).

Verifies:
1. Datetime string parsing & relative date resolution
2. Event creation schema & preview fallback
3. Event updating
4. Event deletion
5. Reading today's events
6. Natural language command execution
"""

import unittest
from datetime import datetime
from calendar_service import (
    create_event,
    delete_event,
    get_today_events,
    parse_and_execute_calendar_request,
    parse_datetime_string,
    update_event,
)
from models import CalendarEvent


class TestGoogleCalendarIntegration(unittest.TestCase):

    def test_parse_datetime_string(self):
        iso_str = "2026-08-10T14:30:00+05:30"
        dt = parse_datetime_string(iso_str)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 10)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 30)

        relative_str = "tomorrow at 3 PM"
        dt_rel = parse_datetime_string(relative_str)
        self.assertEqual(dt_rel.hour, 15)

    def test_create_event_preview(self):
        res = create_event(
            summary="Interview with Candidate",
            start_time="tomorrow at 10 AM",
            attendees=["candidate@example.com"],
            description="Technical interview session",
        )
        self.assertIn(res.get("status"), ["success", "preview"])
        event_dict = res.get("event", {})
        self.assertEqual(event_dict.get("summary"), "Interview with Candidate")
        self.assertIn("candidate@example.com", event_dict.get("attendees", []))

    def test_update_event(self):
        res = update_event(
            event_id="test-event-123",
            summary="Updated Sync Title",
            start_time="2026-08-06T11:00:00+05:30",
        )
        self.assertIn(res.get("status"), ["success", "preview"])

    def test_delete_event(self):
        res = delete_event(event_id="test-event-123")
        self.assertIn(res.get("status"), ["success", "preview"])
        self.assertEqual(res.get("event_id"), "test-event-123")

    def test_get_today_events(self):
        events = get_today_events()
        self.assertIsInstance(events, list)

    def test_parse_and_execute_natural_language(self):
        req1 = "Schedule interview Monday at 10 AM"
        res1 = parse_and_execute_calendar_request(req1)
        self.assertIn(res1.get("status"), ["success", "preview"])

        req2 = "Show my schedule for today"
        res2 = parse_and_execute_calendar_request(req2)
        self.assertIn(res2.get("status"), ["success", "preview"])
        self.assertEqual(res2.get("action"), "read_today")


if __name__ == "__main__":
    unittest.main()
