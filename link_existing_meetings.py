#!/usr/bin/env python3
"""Backfill and link all existing meeting notes in wiki/ with Google Calendar reminders."""

import re
from pathlib import Path
import frontmatter

import config
from calendar_service import create_event, is_schedulable_event

TARGET_ACCOUNT = config.DEFAULT_GOOGLE_ACCOUNT


def backfill_meetings() -> int:
    linked_count = 0
    cleaned_count = 0
    wiki_dir = config.WIKI_DIR

    for path in sorted(wiki_dir.glob("*/*.md")):
        if path.name.startswith("."):
            continue
        try:
            post = frontmatter.load(path)
        except Exception as exc:
            print(f"[SKIP] Could not load {path.name}: {exc}")
            continue

        title = str(post.get("title", path.stem)).strip()
        summary = str(post.get("summary", "")).strip()
        tags = post.get("tags", [])
        if not isinstance(tags, list):
            tags = [str(tags)]
        tags = [str(t) for t in tags]
        body = post.content

        text_to_check = f"{title} {summary} {body}"
        is_schedulable, summary_title, start_dt, reason = is_schedulable_event(text_to_check)

        if not is_schedulable:
            # If note was previously marked as meeting, clean up calendar event properties because it's in the past or not a scheduled event
            if post.get("is_meeting") or post.get("calendar_event_id"):
                post["is_meeting"] = False
                post.metadata.pop("calendar_event_id", None)
                post.metadata.pop("calendar_event_link", None)
                post.metadata.pop("calendar_event_start", None)
                post.metadata.pop("calendar_event_end", None)
                path.write_text(frontmatter.dumps(post), encoding="utf-8")
                cleaned_count += 1
                print(f"[UNSCHEDULED PAST/NON-EVENT NOTE] {path.name} ({reason})")
            continue

        print(f"[FOUND SCHEDULABLE EVENT] Note '{title}' ({path.name})")

        # Ensure 'meeting', 'event', 'scheduled' tags
        for t in ["meeting", "event", "scheduled"]:
            if t not in [x.lower() for x in tags]:
                tags.append(t)

        cal_event_id = post.get("calendar_event_id")
        cal_event_link = post.get("calendar_event_link")
        cal_start = post.get("calendar_event_start")
        cal_end = post.get("calendar_event_end")

        if not cal_event_id:
            # Create Google Calendar event & reminder
            cal_res = create_event(
                summary=title,
                start_time=start_dt,
                description=f"{summary}\n\nLinked SecondSelf Wiki Note: {path.name}",
                target_account=TARGET_ACCOUNT,
            )
            evt = cal_res.get("event", {})
            cal_event_id = evt.get("id")
            cal_event_link = evt.get("html_link")
            cal_start = evt.get("start_time")
            cal_end = evt.get("end_time")
            print(f"  -> Created Google Calendar event & reminder for {TARGET_ACCOUNT}: {cal_event_id}")
            linked_count += 1

        # Update frontmatter
        post["is_meeting"] = True
        post["tags"] = tags
        post["calendar_event_id"] = cal_event_id
        post["calendar_event_link"] = cal_event_link
        post["calendar_account"] = TARGET_ACCOUNT
        post["calendar_event_start"] = cal_start
        post["calendar_event_end"] = cal_end

        path.write_text(frontmatter.dumps(post), encoding="utf-8")
        print(f"  -> Updated frontmatter for {path.name}\n")

    return linked_count


if __name__ == "__main__":
    count = backfill_meetings()
    print(f"[COMPLETED] Scheduled & linked {count} upcoming events to Google Calendar ({TARGET_ACCOUNT}).")
