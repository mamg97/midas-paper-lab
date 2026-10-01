"""Build a transport map from the official Buy The Dip podcast mirror.

YouTube remains the canonical catalogue. The podcast feed is used only as an
alternate public transport for long-form audio when hosted runners cannot read
YouTube captions. No audio or transcript bytes are persisted by this module.
"""

from __future__ import annotations

import argparse
import email.utils
import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"


def normalize_title(value):
    text = str(value or "").lower()
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    text = re.sub(r"\|\s*buy\s+the\s+dip\s+podcast\b", " ", text)
    text = re.sub(r"\bbuy\s+the\s+dip\s+podcast\b", " ", text)
    text = re.sub(r"\bepisodio\s+\d+\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_duration(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    parts = text.split(":")
    try:
        nums = [int(x) for x in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return None


def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    episodes = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        enclosure = item.find("enclosure")
        audio_url = enclosure.attrib.get("url") if enclosure is not None else None
        mime = enclosure.attrib.get("type") if enclosure is not None else None
        length = enclosure.attrib.get("length") if enclosure is not None else None
        duration = item.findtext(f"{{{ITUNES}}}duration")
        pub = (item.findtext("pubDate") or "").strip()
        published = None
        if pub:
            try:
                parsed = email.utils.parsedate_to_datetime(pub)
                published = parsed.date().isoformat()
            except (TypeError, ValueError, OverflowError):
                published = None
        episodes.append({
            "title": title,
            "normalized_title": normalize_title(title),
            "guid": (item.findtext("guid") or "").strip() or None,
            "published_date": published,
            "duration_seconds": parse_duration(duration),
            "audio_url": audio_url,
            "audio_mime": mime,
            "audio_length_bytes": int(length) if str(length or "").isdigit() else None,
        })
    return episodes


def fetch_feed(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": "MIDAS-BuyTheDip/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def similarity(a, b):
    a, b = normalize_title(a), normalize_title(b)
    if not a or not b:
        return 0.0
    seq = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    union = ta | tb
    jac = len(ta & tb) / len(union) if union else 0.0
    return 0.72 * seq + 0.28 * jac


def map_episodes(episodes, youtube_videos, threshold=0.78):
    matches = []
    youtube = [row for row in youtube_videos if row.get("format") != "short"]
    for episode in episodes:
        ranked = sorted(
            ((similarity(episode["title"], row.get("title")), row) for row in youtube),
            key=lambda pair: (-pair[0], pair[1].get("video_id", "")),
        )
        best_score, best = ranked[0] if ranked else (0.0, None)
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        unambiguous = bool(best and best_score >= threshold and (best_score - second_score >= 0.035 or best_score >= 0.95))
        matches.append({
            **episode,
            "youtube_video_id": best.get("video_id") if unambiguous else None,
            "youtube_title": best.get("title") if unambiguous else None,
            "youtube_url": best.get("url") if unambiguous else None,
            "match_score": round(best_score, 6),
            "second_best_score": round(second_score, 6),
            "match_status": "matched" if unambiguous else "unmatched_or_ambiguous",
        })
    return matches


def build(config_path, manifest_path, output_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    mirror = config.get("podcast_mirror") or {}
    feed_url = mirror.get("feed_url")
    if not feed_url:
        raise ValueError("podcast_mirror.feed_url missing")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    episodes = parse_feed(fetch_feed(feed_url))
    mapped = map_episodes(episodes, manifest.get("videos") or [])
    result = {
        "schema_version": 1,
        "provider": mirror.get("provider"),
        "feed_url": feed_url,
        "role": mirror.get("role"),
        "canonical_identity": mirror.get("canonical_identity"),
        "episode_count": len(mapped),
        "with_audio_url": sum(bool(x.get("audio_url")) for x in mapped),
        "matched_to_youtube": sum(x["match_status"] == "matched" for x in mapped),
        "unmatched_or_ambiguous": sum(x["match_status"] != "matched" for x in mapped),
        "episodes": mapped,
    }
    Path(output_path).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("episode_count", "with_audio_url", "matched_to_youtube", "unmatched_or_ambiguous")}, indent=2))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    build(args.config, args.manifest, args.output)


if __name__ == "__main__":
    main()
