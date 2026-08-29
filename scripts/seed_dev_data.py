#!/usr/bin/env python3
"""
Seed a Journiv development instance with realistic journal content.

This exists so that UI work — the Timeline, the reader, the editor, media — can
be exercised against content that looks like a real journal rather than lorem
ipsum. It is idempotent: run it as often as you like.

    JOURNIV_SEED_PASSWORD='choose-a-local-password' \
      python scripts/seed_dev_data.py --api-url http://127.0.0.1:8000/api/v1

Credentials are never hard-coded here. Supply the password through
JOURNIV_SEED_PASSWORD or --password; the account is created on first run.

Media is generated locally: photographs with Pillow, and a short video and
audio clip with ffmpeg. Both are optional — the script degrades with a warning
if either tool is unavailable, and everything else still seeds.

DO NOT run this against a database holding real journal entries.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

DEFAULT_API_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_EMAIL = "dev@example.com"
TIMEZONE = "America/Los_Angeles"


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------


class Api:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None

    def request(self, method: str, path: str, payload: Any = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}", body, headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status == 204:
                    return None
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Surface the API's own message; a bare "HTTP 400" is useless when
            # this script is used to debug a contract change.
            detail = error.read().decode(errors="replace")[:600]
            error.seed_detail = detail  # type: ignore[attr-defined]
            print(f"  ! {method} {path} -> {error.code}: {detail}", file=sys.stderr)
            raise

    def upload(self, path: str, file_path: Path, fields: dict[str, str]) -> Any:
        """Minimal multipart/form-data upload, so there is no requests dependency."""
        boundary = f"----journiv{uuid.uuid4().hex}"
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
            )
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{file_path.name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n".encode()
        )
        parts.append(file_path.read_bytes())
        parts.append(f"\r\n--{boundary}--\r\n".encode())

        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}", b"".join(parts), headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)

    def sign_in(self, email: str, password: str) -> bool:
        """Returns True when a new account was created."""
        created = False
        try:
            self.request("POST", "/auth/login", {"email": email, "password": password})
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise
            self.request(
                "POST",
                "/auth/register",
                {"email": email, "password": password, "name": "Journiv Dev"},
            )
            created = True
        tokens = self.request(
            "POST", "/auth/login", {"email": email, "password": password}
        )
        self.token = tokens["access_token"]
        return created


# --------------------------------------------------------------------------
# generated media
# --------------------------------------------------------------------------

PALETTES = {
    "lake": [(58, 78, 96), (128, 156, 168), (214, 196, 158), (36, 48, 62)],
    "kyoto": [(196, 72, 54), (228, 112, 76), (120, 64, 58), (238, 196, 150)],
    "beach": [(226, 214, 190), (146, 180, 190), (96, 132, 150), (240, 236, 224)],
    "trail": [(84, 104, 66), (140, 158, 104), (58, 72, 50), (198, 204, 170)],
    "city": [(58, 68, 88), (120, 138, 150), (210, 180, 150), (36, 42, 56)],
    "tiles": [(70, 120, 150), (230, 232, 228), (180, 200, 214), (120, 160, 180)],
}


def make_photos(out_dir: Path) -> dict[str, Path]:
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        print("  ! Pillow not available — skipping photo generation", file=sys.stderr)
        return {}

    import random

    photos: dict[str, Path] = {}
    for name, colours in PALETTES.items():
        target = out_dir / f"{name}.jpg"
        width, height = 1600, 1067
        # Portrait for one of them, so layout work sees a tall photograph.
        if name == "tiles":
            width, height = 1067, 1600
        image = Image.new("RGB", (width, height), colours[0])
        draw = ImageDraw.Draw(image)
        random.seed(name)
        for _ in range(90):
            colour = random.choice(colours)
            x, y = random.randint(-200, width), random.randint(-200, height)
            draw.ellipse(
                [x, y, x + random.randint(120, 900), y + random.randint(90, 700)],
                fill=tuple(
                    min(255, max(0, value + random.randint(-28, 28))) for value in colour
                ),
            )
        image = image.filter(ImageFilter.GaussianBlur(38))
        image.save(target, quality=88)
        photos[name] = target
    return photos


def make_video(out_dir: Path) -> Path | None:
    if not shutil.which("ffmpeg"):
        print("  ! ffmpeg not available — skipping video", file=sys.stderr)
        return None
    target = out_dir / "sunset.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "gradients=size=960x540:duration=4:speed=0.06",
            "-t", "4", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(target),
        ],
        check=True,
    )
    return target


def make_audio(out_dir: Path) -> Path | None:
    if not shutil.which("ffmpeg"):
        return None
    target = out_dir / "water.m4a"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "anoisesrc=d=6:c=pink:a=0.06",
            "-c:a", "aac", "-b:a", "96k",
            str(target),
        ],
        check=True,
    )
    return target


# --------------------------------------------------------------------------
# content
# --------------------------------------------------------------------------


def paragraph(text: str) -> list[dict]:
    return [{"insert": text}, {"insert": "\n"}]


def line(text: str, **attributes: Any) -> list[dict]:
    return [{"insert": text}, {"insert": "\n", "attributes": attributes}]


def runs(*pieces: tuple[str, dict | None]) -> list[dict]:
    ops: list[dict] = []
    for text, attributes in pieces:
        ops.append({"insert": text, **({"attributes": attributes} if attributes else {})})
    ops.append({"insert": "\n"})
    return ops


def document(*groups: list[dict]) -> dict:
    ops: list[dict] = []
    for group in groups:
        ops.extend(group)
    return {"ops": ops}


NOTE_ONLY_TEXT = (
    "Saw a heron on the way to the store. Want to write about this properly later."
)


def _first_text(delta: dict) -> str:
    for op in delta.get("ops", []):
        insert = op.get("insert")
        if isinstance(insert, str) and insert.strip():
            return insert.strip()[:60]
    return ""


def _spec_signature(spec: dict) -> str:
    return spec["title"] or _first_text(spec["content"])


def _signatures(moments: list[dict]) -> set[str]:
    """Titles plus first-paragraph prefixes, so untitled Moments dedupe too."""
    found: set[str] = set()
    for moment in moments:
        entry = moment.get("entry") or {}
        if entry.get("title"):
            found.add(entry["title"])
        text = (entry.get("content_plain_text") or "").strip()
        if text:
            found.add(text[:60])
    return found


def when(days_ago: int, hour: int, minute: int) -> str:
    moment = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)
    return moment.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


JOURNALS = [
    ("Personal", "#6366F1", "Everyday life, thinking out loud."),
    ("Travel", "#14B8A6", "Trips, trains and long walks."),
    ("Family", "#F43F5E", "The people who make the noise."),
    ("Running", "#84CC16", "Training log and race notes."),
    ("Work notes", "#64748B", "Standups, decisions, retros."),
]

PEOPLE = [("Maya", None), ("Charles", "Dad"), ("Sarah Chen", None), ("Tom Whitfield", None)]


def moment_specs() -> list[dict]:
    return [
        dict(
            days=1, hour=21, minute=40, journal="Personal", title="The long way home",
            tags=["evening", "walking"], people=[], mood="Meh", photo="city",
            weather="Clear 14°C", location="Bernal Heights, San Francisco",
            lat=37.7396, lon=-122.4156, pinned=True,
            content=document(
                paragraph("I took the long way home tonight, up and over the hill instead of straight down Mission. There was no reason for it. The bus was right there. I just wanted the extra twenty minutes."),
                paragraph("From the top you can see the whole grid lit up, and the fog coming in over Twin Peaks like something being poured. I sat on the bench near the radio tower until my hands got cold."),
                line("What I keep coming back to", header=2),
                paragraph("There is a version of this year where I did everything right and still felt like this. I am trying to make peace with that being possible."),
                line("The city looked completely indifferent to me, and somehow that was the comforting part.", blockquote=True),
                line("Three things I noticed", header=3),
                line("The eucalyptus smell after rain", list="bullet"),
                line("Someone practicing trumpet, badly, with total commitment", list="bullet"),
                line("A dog wearing a raincoat, deeply unimpressed", list="bullet"),
                paragraph("I got home at nine, ate cereal standing up, and felt fine. Not good exactly. Fine. I will take fine."),
            ),
        ),
        dict(
            days=2, hour=7, minute=15, journal="Running", title="Six miles, easy",
            tags=["training", "morning"], people=[], mood=None, photo="trail",
            weather="Fog 11°C", location="Golden Gate Park",
            content=document(
                paragraph("Six easy miles around the park loop. Legs felt heavy for the first two and then remembered what they were for."),
                line("Splits", header=3),
                *[line(f"Mile {index} — {pace}", list="ordered") for index, pace in
                  enumerate(["9:12", "8:58", "8:41", "8:39", "8:34", "8:20"], start=1)],
                runs(("Negative split without trying. ", None), ("That has not happened since March.", {"bold": True})),
            ),
        ),
        dict(
            days=4, hour=19, minute=5, journal="Family",
            title="Dad on the phone for fifty minutes",
            tags=["family", "phone"], people=["Charles"], mood="Good",
            content=document(
                paragraph("Dad called and talked for fifty minutes about a fence. Not his fence. The neighbour's fence. The neighbour is apparently building it four inches onto the property line and Dad has measured it twice."),
                paragraph("Halfway through I realised I was not really listening to the fence. I was listening to him being completely absorbed in something, which he has not been in a while."),
                runs(("He said, ", None), ("\"I am not going to say anything, I just want it on the record.\"", {"italic": True}), (" On the record with whom, Dad? Me. I am the record.", None)),
            ),
        ),
        dict(
            days=6, hour=14, minute=30, journal="Work notes", title=None,
            tags=["retro"], people=["Sarah Chen", "Tom Whitfield"], mood=None,
            content=document(
                paragraph("Retro ran long again. The migration is the elephant nobody wants to name, so we spent thirty minutes on ticket hygiene instead."),
                line("Sarah made the actual point: we are optimising the process around a decision we have not made.", blockquote=True),
                paragraph("Writing it here so I remember to say it out loud on Thursday."),
            ),
        ),
        dict(
            days=9, hour=11, minute=0, journal="Travel", title="Kyoto, day three",
            tags=["kyoto", "japan", "trains"], people=["Maya"], mood="Awesome",
            photo="kyoto", weather="Rain 18°C", location="Fushimi Inari, Kyoto",
            lat=34.9671, lon=135.7727, pinned=True,
            content=document(
                paragraph("Rain the whole day, which turned out to be the best thing that could have happened. We went up Fushimi Inari at seven in the morning and for the first forty minutes we had the gates almost entirely to ourselves."),
                paragraph("Maya counted torii out loud until she lost track somewhere past two hundred, and then we just walked. The rain on the vermilion made the whole tunnel feel like it was breathing."),
                line("Notes for next time", header=2),
                line("Go early. Seven is not early enough. Six is early enough.", list="bullet"),
                line("The upper shrine is worth the climb; most people turn back at the halfway viewpoint.", list="bullet"),
                line("There is a tiny place near the base that does grilled sparrow. Maya was horrified. I was curious. We got udon.", list="bullet"),
                paragraph("We came down at eleven soaked through and sat in a coffee place for two hours drying out, watching the tour groups arrive in waves."),
                runs(("Best day of the trip so far and it was the one we did not plan.", {"bold": True})),
            ),
        ),
        dict(
            days=15, hour=22, minute=10, journal="Personal", title="Insomnia, again",
            tags=["sleep"], people=[], mood="Bad",
            content=document(
                paragraph("Third night this week. I know the drill by now: do not look at the clock, do not do the maths on how many hours are left, do not start planning tomorrow."),
                paragraph("I did all three."),
            ),
        ),
        dict(
            days=23, hour=9, minute=30, journal="Running",
            title="Half marathon — 1:52:11", tags=["race", "training"],
            people=["Sarah Chen"], mood="Awesome", photo="lake",
            weather="Cool 9°C", location="Lake Merced", lat=37.7180, lon=-122.4939,
            pinned=True,
            content=document(
                paragraph("Went out too fast, obviously. Everyone does. The first three miles felt free and the last three felt like a negotiation with someone who does not like me."),
                line("1:52:11.", header=1),
                paragraph("Four minutes off the target and I do not care even slightly. Two years ago I could not run the length of the block without stopping to pretend I was checking my phone."),
                line("Sarah waited at the finish with a coffee and did not say anything about the time, which was the correct call.", blockquote=True),
                line("What worked", header=3),
                line("The long slow runs. Boring, unglamorous, entirely the reason.", list="bullet"),
                line("New shoes, broken in properly instead of the week before.", list="bullet"),
            ),
        ),
        dict(
            days=38, hour=20, minute=0, journal="Personal", title="Nothing much",
            tags=[], people=[], mood=None, weather="Clear 17°C",
            content=document(paragraph("Quiet day. Made soup. Read forty pages. That is the whole entry and it is allowed to be.")),
        ),
        dict(
            days=74, hour=18, minute=20, journal="Family",
            title="Sunday, the whole day", tags=["family", "sunday"],
            people=["Maya", "Charles", "Sarah Chen"], mood="Good", photo="beach",
            weather="Warm 22°C", location="Ocean Beach", lat=37.7594, lon=-122.5107,
            content=document(
                paragraph("Everyone at the beach. Dad wore actual shoes onto sand and refused to acknowledge this was a mistake at any point during the four hours."),
                paragraph("Maya spent ninety minutes building something she described as 'a house for a crab, but the crab is optional'. No crab was ever located."),
                line("Dad, watching her rebuild the same wall for the fourth time: \"She gets that from you.\"", blockquote=True),
            ),
        ),
    ]


# --------------------------------------------------------------------------
# seeding
# --------------------------------------------------------------------------


def wait_for_processing(api: Api, moment_id: str, expected: int, timeout: float = 45.0) -> None:
    """Media processing is asynchronous; give the worker a chance to finish."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        items = api.request("GET", f"/moments/{moment_id}/media")
        statuses = [item.get("upload_status") for item in items]
        if len(items) >= expected and all(s in ("completed", "failed") for s in statuses):
            return
        time.sleep(1.0)
    print(f"  ! media for {moment_id[:8]} still processing after {timeout:.0f}s", file=sys.stderr)


def seed(api: Api, media_dir: Path) -> None:
    print("Generating media…")
    photos = make_photos(media_dir)
    video = make_video(media_dir)
    audio = make_audio(media_dir)

    print("Journals…")
    journals = {j["title"]: j for j in api.request("GET", "/journals/")}
    for title, colour, description in JOURNALS:
        if title not in journals:
            journals[title] = api.request(
                "POST", "/journals/",
                {"title": title, "color": colour, "description": description},
            )
    print(f"  {len(journals)} journals")

    print("People…")
    people = {p["name"]: p for p in api.request("GET", "/people/")}
    for name, nickname in PEOPLE:
        if name not in people:
            people[name] = api.request("POST", "/people/", {"name": name, "nickname": nickname})

    moods = {m["name"]: m["id"] for m in api.request("GET", "/moods/")}

    existing = api.request("GET", "/moments?limit=200&include_empty=true")["items"]
    seen = _signatures(existing)

    print("Moments…")
    created = 0
    for spec in moment_specs():
        # Content-derived signature, so untitled Moments dedupe too. Timestamps
        # are relative to "now" and therefore cannot be used as a key.
        if _spec_signature(spec) in seen:
            continue
        body: dict[str, Any] = {
            "logged_at_utc": when(spec["days"], spec["hour"], spec["minute"]),
            "logged_timezone": TIMEZONE,
            "is_pinned": spec.get("pinned", False),
            "entry": {
                "title": spec["title"],
                "journal_id": journals[spec["journal"]]["id"],
                "content_delta": spec["content"],
            },
        }
        if spec.get("weather"):
            body["weather_summary"] = spec["weather"]
        if spec.get("location"):
            body["location_json"] = {"name": spec["location"]}
        if spec.get("lat"):
            body["latitude"] = spec["lat"]
            body["longitude"] = spec["lon"]
        moment = api.request("POST", "/moments", body)

        # `primary_mood_id` is rejected on create unless it is already part of
        # the moment's mood set, but it is accepted on update.
        if spec.get("mood") and spec["mood"] in moods:
            api.request(
                "PUT", f"/moments/{moment['id']}",
                {"primary_mood_id": moods[spec["mood"]]},
            )
        if spec["tags"]:
            api.request("POST", f"/moments/{moment['id']}/tags", spec["tags"])
        if spec["people"]:
            api.request(
                "PUT", f"/moments/{moment['id']}/people",
                {"person_ids": [people[name]["id"] for name in spec["people"]]},
            )
        if spec.get("photo") and spec["photo"] in photos:
            api.upload(
                "/media/upload", photos[spec["photo"]],
                {"moment_id": moment["id"], "alt_text": spec.get("location") or spec["title"] or ""},
            )
            wait_for_processing(api, moment["id"], 1)
        created += 1
    print(f"  {created} moments created")

    # --- sparse Moment scenarios from DESIGN.md §10 ----------------------
    print("Sparse Moments…")
    current = api.request("GET", "/moments?limit=200&include_empty=true")["items"]
    notes = {(m.get("note") or "").strip() for m in current}
    if NOTE_ONLY_TEXT not in notes:
        api.request("POST", "/moments", {
            "logged_at_utc": when(3, 15, 0), "logged_timezone": TIMEZONE,
            "note": NOTE_ONLY_TEXT,
        })
        print("  note-only moment")

    media_only_exists = any(
        not m.get("entry") and not (m.get("note") or "").strip() and (m.get("media_count") or 0) > 0
        for m in current
    )
    if not media_only_exists and photos:
        moment = api.request("POST", "/moments", {
            "logged_at_utc": when(21, 10, 30), "logged_timezone": TIMEZONE,
            "location_json": {"name": "Ferry Building, San Francisco"},
        })
        for name in ("beach", "tiles"):
            if name in photos:
                api.upload("/media/upload", photos[name],
                           {"moment_id": moment["id"], "alt_text": "Saturday at the water"})
        wait_for_processing(api, moment["id"], 2)
        print("  media-only moment")

    # --- inline media -----------------------------------------------------
    print("Inline media…")
    if "The tiles, close up" not in _signatures(current) and photos.get("tiles"):
        moment = api.request("POST", "/moments", {
            "logged_at_utc": when(46, 16, 40), "logged_timezone": TIMEZONE,
            "location_json": {"name": "Alfama, Lisbon"}, "weather_summary": "Sunny 24°C",
            "entry": {
                "title": "The tiles, close up",
                "journal_id": journals["Travel"]["id"],
                "content_delta": document(paragraph("Placeholder while the media uploads.")),
            },
        })
        uploads = []
        uploaded = api.upload("/media/upload", photos["tiles"],
                              {"moment_id": moment["id"], "alt_text": "A tiled doorway in Alfama"})
        uploads.append(("image", uploaded["id"]))
        if video:
            uploaded = api.upload("/media/upload", video,
                                  {"moment_id": moment["id"], "alt_text": "Light moving on the tiles"})
            uploads.append(("video", uploaded["id"]))
        wait_for_processing(api, moment["id"], len(uploads))

        ops: list[dict] = []
        ops += paragraph("Spent the afternoon photographing doorways. Every third building has tile work that would be behind glass anywhere else, and here it is holding up a laundry line.")
        for kind, media_id in uploads:
            # Persisted form is a bare media id. The backend hydrates it to a
            # signed URL on read and normalizes it back on write.
            ops.append({"insert": {kind: media_id}})
            ops.append({"insert": "\n"})
        ops += runs(("This one had a ", None), ("cracked", {"italic": True}),
                    (" corner that someone had repaired with a slightly wrong blue. I liked it more for that.", None))
        api.request("PUT", f"/moments/{moment['id']}",
                    {"entry_update": {"content_delta": {"ops": ops}}})
        print(f"  inline entry with {len(uploads)} media item(s)")

    if audio:
        print("  (audio clip generated at %s for manual attachment tests)" % audio.name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=os.environ.get("JOURNIV_SEED_PASSWORD"))
    parser.add_argument("--media-dir", default=None,
                        help="Where to write generated media (default: a temp dir)")
    args = parser.parse_args()

    if not args.password:
        raise SystemExit(
            "A password is required. Set JOURNIV_SEED_PASSWORD or pass --password.\n"
            "Credentials are deliberately not stored in this file."
        )

    api = Api(args.api_url)
    try:
        created = api.sign_in(args.email, args.password)
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"Sign-in failed with HTTP {error.code}. If the account exists with a "
            "different password, pass --email to use a new one."
        ) from None
    except urllib.error.URLError as error:
        raise SystemExit(f"Cannot reach {args.api_url}: {error.reason}") from None

    print(f"Account {args.email}: {'created' if created else 'existing'}")

    media_dir = Path(args.media_dir) if args.media_dir else Path(tempfile.mkdtemp(prefix="journiv-seed-"))
    media_dir.mkdir(parents=True, exist_ok=True)
    seed(api, media_dir)
    print(f"\nDone. Sign in as {args.email}.")
    print(f"Generated media kept in {media_dir}")


if __name__ == "__main__":
    main()
