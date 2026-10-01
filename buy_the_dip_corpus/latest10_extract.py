"""Extract transcripts for the latest Buy The Dip uploads.

The transcript text is intentionally ephemeral: GitHub Actions uploads it as a
short-lived artifact for semantic review, while Git only receives metadata.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


CHANNEL_ID = "UCS5I8A7UAu43QgFxxu8VRbQ"
CHANNEL_URL = "https://www.youtube.com/@Buy_The_Dip"
RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rss_latest(limit=10):
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
    root = ET.fromstring(data)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }
    items = []
    for entry in root.findall("atom:entry", ns):
        vid = entry.findtext("yt:videoId", default="", namespaces=ns)
        title = entry.findtext("atom:title", default=vid, namespaces=ns)
        published = entry.findtext("atom:published", default="", namespaces=ns)
        if vid:
            items.append({
                "video_id": vid,
                "title": title,
                "published_at": published or None,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "source": "youtube_rss",
            })
        if len(items) >= limit:
            break
    return items


def _ytdlp_latest(limit=10):
    cmd = [
        "yt-dlp", "--flat-playlist", "--playlist-end", str(limit),
        "--dump-json", "--no-warnings", f"{CHANNEL_URL}/videos",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=True)
    items = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        vid = str(row.get("id") or "")
        if not vid:
            continue
        items.append({
            "video_id": vid,
            "title": row.get("title") or vid,
            "published_at": None,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "source": "yt_dlp_videos_tab",
        })
    return items[:limit]


def inventory(output, limit=10):
    errors = []
    items = []
    try:
        items = _rss_latest(limit)
    except Exception as exc:
        errors.append(f"rss:{type(exc).__name__}:{exc}")
    if len(items) < limit:
        try:
            fallback = _ytdlp_latest(limit)
            seen = {x["video_id"] for x in items}
            items.extend(x for x in fallback if x["video_id"] not in seen)
        except Exception as exc:
            errors.append(f"yt_dlp:{type(exc).__name__}:{exc}")
    items = items[:limit]
    if len(items) < limit:
        raise RuntimeError(f"Only {len(items)} latest videos resolved; errors={errors}")
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "channel_id": CHANNEL_ID,
        "channel_url": CHANNEL_URL,
        "count": len(items),
        "videos": items,
        "errors": errors,
    }
    _write_json(output, payload)
    matrix = {"include": [{"video_id": x["video_id"]} for x in items]}
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as stream:
            stream.write("matrix=" + json.dumps(matrix, separators=(",", ":")) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _clean_caption_text(text):
    lines, out, previous = text.splitlines(), [], None
    for raw in lines:
        line = raw.strip()
        if not line or line == "WEBVTT" or "-->" in line or re.fullmatch(r"\d+", line):
            continue
        if line.startswith(("Kind:", "Language:", "NOTE", "STYLE", "REGION")):
            continue
        line = re.sub(r"<[^>]+>", " ", line)
        line = html.unescape(line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line == previous:
            continue
        out.append(line)
        previous = line
    return "\n".join(out).strip()


def _youtube_transcript_api(video_id):
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id, languages=["es", "es-ES", "en"])
    snippets = []
    language = getattr(transcript, "language_code", None)
    for item in transcript:
        text = getattr(item, "text", None)
        if text is None and isinstance(item, dict):
            text = item.get("text")
        if text:
            snippets.append(str(text).strip())
    result = "\n".join(x for x in snippets if x).strip()
    if not result:
        raise RuntimeError("empty transcript api result")
    return result, language


def _yt_dlp_subtitles(video_id, workdir):
    template = str(Path(workdir) / "%(id)s.%(language)s.%(ext)s")
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
        "--sub-langs", "es.*,es,en.*", "--sub-format", "vtt",
        "--no-warnings", "-o", template, url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    files = sorted(Path(workdir).glob(f"{video_id}.*.vtt"))
    if not files:
        raise RuntimeError("no vtt from yt-dlp: " + " | ".join(proc.stderr.splitlines()[-6:]))
    # Prefer Spanish/original variants.
    files.sort(key=lambda p: (0 if ".es" in p.name else 1, len(p.name), p.name))
    text = _clean_caption_text(files[0].read_text(encoding="utf-8", errors="ignore"))
    if not text:
        raise RuntimeError("empty vtt")
    lang = files[0].name[len(video_id)+1:-4]
    return text, lang


def _whisper_fallback(video_id, workdir):
    url = f"https://www.youtube.com/watch?v={video_id}"
    audio = Path(workdir) / f"{video_id}.m4a"
    cmd = [
        "yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio",
        "--no-playlist", "--no-warnings", "-o", str(audio), url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or not audio.exists():
        raise RuntimeError("audio download failed: " + " | ".join(proc.stderr.splitlines()[-8:]))

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "faster-whisper>=1.1,<2"],
            check=True, timeout=600,
        )
        from faster_whisper import WhisperModel

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio), language="es", vad_filter=True, beam_size=3,
        condition_on_previous_text=True,
    )
    lines = []
    for segment in segments:
        t = re.sub(r"\s+", " ", str(segment.text)).strip()
        if t:
            lines.append(t)
    text = "\n".join(lines).strip()
    if not text:
        raise RuntimeError("empty whisper transcript")
    return text, getattr(info, "language", "es")


def transcribe(video_id, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    attempts = []
    method = language = None
    transcript = None

    try:
        transcript, language = _youtube_transcript_api(video_id)
        method = "youtube-transcript-api"
    except Exception as exc:
        attempts.append({"method": "youtube-transcript-api", "error": f"{type(exc).__name__}: {exc}"})

    with tempfile.TemporaryDirectory(prefix=f"btd-{video_id}-") as workdir:
        if transcript is None:
            try:
                transcript, language = _yt_dlp_subtitles(video_id, workdir)
                method = "yt-dlp-captions"
            except Exception as exc:
                attempts.append({"method": "yt-dlp-captions", "error": f"{type(exc).__name__}: {exc}"})
        if transcript is None:
            try:
                transcript, language = _whisper_fallback(video_id, workdir)
                method = "faster-whisper-base"
            except Exception as exc:
                attempts.append({"method": "faster-whisper-base", "error": f"{type(exc).__name__}: {exc}"})

    success = bool(transcript)
    if success:
        (output / "transcript.txt").write_text(transcript + "\n", encoding="utf-8")
    meta = {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "success": success,
        "method": method,
        "language": language,
        "word_count": len(transcript.split()) if transcript else 0,
        "character_count": len(transcript) if transcript else 0,
        "attempts": attempts,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(output / "metadata.json", meta)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if not success:
        raise SystemExit(2)


def aggregate(inventory_path, artifacts_dir, output):
    inventory_data = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    rows = []
    for video in inventory_data["videos"]:
        vid = video["video_id"]
        matches = list(Path(artifacts_dir).rglob(f"{vid}/metadata.json"))
        if not matches:
            matches = [p for p in Path(artifacts_dir).rglob("metadata.json") if p.parent.name == vid]
        meta = None
        if matches:
            meta = json.loads(matches[0].read_text(encoding="utf-8"))
        rows.append({**video, **(meta or {
            "success": False, "method": None, "language": None,
            "word_count": 0, "character_count": 0,
            "attempts": [{"method": "aggregate", "error": "artifact missing"}],
        })})
    report = {
        "schema_version": 1,
        "source": "Buy The Dip latest-10 transcript extraction test",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "success_count": sum(bool(x.get("success")) for x in rows),
        "failure_count": sum(not bool(x.get("success")) for x in rows),
        "videos": rows,
        "note": "Transcript text is intentionally not committed; only extraction metadata persists.",
    }
    _write_json(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inventory")
    p.add_argument("--output", required=True)
    p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("transcribe")
    p.add_argument("--video-id", required=True)
    p.add_argument("--output-dir", required=True)
    p = sub.add_parser("aggregate")
    p.add_argument("--inventory", required=True)
    p.add_argument("--artifacts-dir", required=True)
    p.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "inventory":
        inventory(args.output, args.limit)
    elif args.command == "transcribe":
        transcribe(args.video_id, args.output_dir)
    else:
        aggregate(args.inventory, args.artifacts_dir, args.output)


if __name__ == "__main__":
    main()
