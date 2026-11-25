from datetime import datetime, timezone
import math
import re
from urllib.parse import parse_qs, urlsplit

from requests import Session
from requests.exceptions import ConnectionError, Timeout
from youtube_transcript_api import (
    NoTranscriptFound, TranscriptsDisabled, VideoUnavailable, YouTubeTranscriptApi,
)
from youtube_transcript_api._errors import CouldNotRetrieveTranscript

from .schemas import PipelineError, Segment, TranscriptSnapshot, version


class CaptionHTTP(Session):
    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", 15)
        return super().request(*args, **kwargs)


def parse_video(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    try:
        url = urlsplit(value)
        if url.scheme not in ("http", "https") or url.username or url.password or url.port:
            raise ValueError
        if url.hostname in ("youtu.be", "www.youtu.be"):
            video = url.path.removeprefix("/")
        elif url.hostname in ("youtube.com", "www.youtube.com", "m.youtube.com", "www.youtube-nocookie.com"):
            if url.path == "/watch":
                ids = parse_qs(url.query).get("v", [])
                video = ids[0] if len(ids) == 1 else ""
            else:
                match = re.fullmatch(r"/(?:embed|shorts|live)/([A-Za-z0-9_-]{11})/?", url.path)
                video = match[1] if match else ""
        else:
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
            raise ValueError
        return video
    except ValueError:
        raise PipelineError("invalid_video", "Enter a valid YouTube URL or 11-character video ID.") from None


def map_timestamps(video_id, language, generated, rows, fetched_at=None):
    video_id = parse_video(video_id)
    if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z0-9-]{2,20}", language):
        raise PipelineError("invalid_language", "Use a caption language code such as en or en-US.")
    if type(generated) is not bool:
        raise PipelineError("invalid_transcript", "Caption track metadata is invalid.")
    records = []
    previous = -1
    for row in rows:
        try:
            text, start, duration = row["text"], row["start"], row["duration"]
        except (KeyError, TypeError):
            raise PipelineError("invalid_transcript", "Captions are missing text or timing fields.") from None
        if (not isinstance(text, str) or not text.strip()
                or isinstance(start, bool) or isinstance(duration, bool)
                or not isinstance(start, (int, float)) or not isinstance(duration, (int, float))
                or not math.isfinite(start) or not math.isfinite(duration)
                or start < previous or start < 0 or duration < 0 or not math.isfinite(start + duration)):
            raise PipelineError("invalid_transcript", "Captions contain invalid text, timing, or ordering.")
        records.append({"text": text, "start": float(start), "end": float(start + duration)})
        previous = start
    if not records:
        raise PipelineError("empty_transcript", "The selected caption track is empty.")
    if len(records) > 30000 or sum(len(s["text"]) for s in records) > 500000:
        raise PipelineError("source_limit", "This caption track exceeds the pilot's size limit.")
    source = version([video_id, language, generated, records])
    segments = tuple(Segment(f"{source[:16]}-s{i}", **row) for i, row in enumerate(records))
    return TranscriptSnapshot(video_id, language, generated, source,
                              fetched_at or datetime.now(timezone.utc).isoformat(), segments)


def fetch_transcript(video_id: str, language: str = "en") -> TranscriptSnapshot:
    video_id = parse_video(video_id)
    if not re.fullmatch(r"[A-Za-z0-9-]{2,20}", language):
        raise PipelineError("invalid_language", "Use a caption language code such as en or en-US.")
    with CaptionHTTP() as client:
        api = YouTubeTranscriptApi(http_client=client)
        for attempt in range(2):
            try:
                track = api.fetch(video_id, languages=[language])
                return map_timestamps(video_id, track.language_code, track.is_generated,
                                      ({"text": s.text, "start": s.start, "duration": s.duration} for s in track.snippets))
            except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable):
                raise PipelineError("captions_unavailable", f"No accessible {language} captions for this video.") from None
            except (ConnectionError, Timeout):
                if attempt:
                    raise PipelineError("caption_transient", "Caption access timed out; try again later.") from None
            except CouldNotRetrieveTranscript:
                raise PipelineError("caption_access", "YouTube could not supply captions from this server.") from None
