#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CHANNEL_URL = "https://www.youtube.com/@Buy_The_Dip"
MANIFEST_URL = "https://raw.githubusercontent.com/mamg97/midas-paper-lab/main/buy_the_dip_state/manifest.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def detect_drive_root() -> Path:
    override = os.environ.get("BTD_OUT")
    if override:
        return Path(override).expanduser().resolve()

    candidates = sorted(glob.glob(
        str(Path.home() / "Library/CloudStorage/GoogleDrive-*/My Drive/DOCUMENTOS/MIDAS/BUY THE DIP - CORPUS MIDAS")
    ))
    if candidates:
        return Path(candidates[0]) / "FULL_CORPUS"

    fallback = Path.home() / "Documents/MIDAS_BUY_THE_DIP/FULL_CORPUS"
    print("⚠️ No detecto Google Drive for Desktop. Guardaré en:", fallback)
    print("   Si quieres otra ruta: BTD_OUT='/ruta/destino' python3 local_transcribe.py")
    return fallback


def load_manifest():
    with urllib.request.urlopen(MANIFEST_URL, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    videos = data.get("videos") or []
    if len(videos) < 290:
        raise RuntimeError(f"Manifest inesperadamente corto: {len(videos)}")
    return videos


def transcript_api(video_id):
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    tr = api.fetch(video_id, languages=["es", "es-ES", "en"])
    lines = []
    for item in tr:
        txt = getattr(item, "text", None)
        if txt is None and isinstance(item, dict):
            txt = item.get("text")
        if txt:
            txt = re.sub(r"\s+", " ", str(txt)).strip()
            if txt:
                lines.append(txt)
    text = "\n".join(lines).strip()
    if not text:
        raise RuntimeError("transcript-api devolvió texto vacío")
    return text, getattr(tr, "language_code", None) or "unknown", "youtube-transcript-api"


def run(cmd, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def yt_dlp_captions(video_id, work):
    url = f"https://www.youtube.com/watch?v={video_id}"
    template = str(Path(work) / "%(id)s.%(language)s.%(ext)s")
    p = run([
        "yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
        "--sub-langs", "es.*,es,en.*", "--sub-format", "vtt",
        "--no-playlist", "--no-warnings", "-o", template, url,
    ], 300)
    files = sorted(Path(work).glob(f"{video_id}.*.vtt"))
    if not files:
        raise RuntimeError((p.stderr or p.stdout)[-1800:])

    def clean(path):
        out, prev = [], None
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line == "WEBVTT" or "-->" in line or re.fullmatch(r"\d+", line):
                continue
            if line.startswith(("Kind:", "Language:", "NOTE", "STYLE", "REGION")):
                continue
            line = re.sub(r"<[^>]+>", " ", line)
            line = re.sub(r"\s+", " ", line).strip()
            if line and line != prev:
                out.append(line)
                prev = line
        return "\n".join(out).strip()

    files.sort(key=lambda p: (0 if ".es" in p.name else 1, len(p.name), p.name))
    text = clean(files[0])
    if not text:
        raise RuntimeError("VTT vacío")
    lang = files[0].name[len(video_id)+1:-4]
    return text, lang, "yt-dlp-captions"


def download_audio(video_id, work):
    url = f"https://www.youtube.com/watch?v={video_id}"
    out = Path(work) / f"{video_id}.m4a"
    p = run([
        "yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio",
        "--no-playlist", "--no-warnings", "-o", str(out), url,
    ], 900)
    if p.returncode != 0 or not out.exists():
        raise RuntimeError((p.stderr or p.stdout)[-1800:])
    return out


_whisper = None
def whisper_audio(audio):
    global _whisper
    from faster_whisper import WhisperModel
    if _whisper is None:
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = _whisper.transcribe(str(audio), language="es", vad_filter=True, beam_size=3)
    lines = [re.sub(r"\s+", " ", str(s.text)).strip() for s in segments]
    text = "\n".join(x for x in lines if x).strip()
    if not text:
        raise RuntimeError("Whisper devolvió texto vacío")
    return text, getattr(info, "language", "es"), "faster-whisper-small"


def looks_blocked(msg: str) -> bool:
    x = msg.lower()
    needles = [
        "requestblocked", "ipblocked", "sign in to confirm you’re not a bot",
        "sign in to confirm you're not a bot", "confirm you’re not a bot",
        "confirm you're not a bot",
    ]
    return any(n in x for n in needles)


def extract(video_id):
    attempts = []
    try:
        return (*transcript_api(video_id), attempts)
    except Exception as exc:
        attempts.append({"method": "youtube-transcript-api", "error": f"{type(exc).__name__}: {exc}"[:2500]})

    with tempfile.TemporaryDirectory(prefix=f"btd-{video_id}-") as work:
        try:
            return (*yt_dlp_captions(video_id, work), attempts)
        except Exception as exc:
            attempts.append({"method": "yt-dlp-captions", "error": f"{type(exc).__name__}: {exc}"[:2500]})

        try:
            audio = download_audio(video_id, work)
            return (*whisper_audio(audio), attempts)
        except Exception as exc:
            attempts.append({"method": "audio+whisper", "error": f"{type(exc).__name__}: {exc}"[:2500]})

    blocked = all(looks_blocked(a["error"]) for a in attempts if a.get("error"))
    raise RuntimeError(json.dumps({"blocked": blocked, "attempts": attempts}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-new", type=int, default=0, help="0 = todos los pendientes")
    ap.add_argument("--sleep", type=float, default=1.5)
    args = ap.parse_args()

    root = detect_drive_root()
    videos_root = root / "videos"
    videos_root.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    completed = 0
    for v in manifest:
        p = videos_root / v["video_id"] / "transcript.txt"
        if p.exists() and p.stat().st_size > 100:
            completed += 1

    pending = [v for v in manifest if not (videos_root / v["video_id"] / "transcript.txt").exists()]
    if args.max_new:
        pending = pending[:args.max_new]

    print(f"📊 Completados al comenzar: {completed}/{len(manifest)}")
    print(f"⏳ Pendientes en esta ejecución: {len(pending)}")

    done_this_run = 0
    for idx, video in enumerate(pending, 1):
        vid = video["video_id"]
        folder = videos_root / vid
        folder.mkdir(parents=True, exist_ok=True)
        print(f"\n▶️ {idx}/{len(pending)} · {video.get('title')}")
        started = time.time()
        try:
            text, lang, method, attempts = extract(vid)
            (folder / "transcript.txt").write_text(text + "\n", encoding="utf-8")
            meta = {
                **video, "success": True, "method": method, "language": lang,
                "word_count": len(text.split()), "character_count": len(text),
                "elapsed_seconds": round(time.time()-started, 2),
                "attempts": attempts, "completed_at_utc": now(),
            }
            atomic_json(folder / "metadata.json", meta)
            done_this_run += 1
            print(f"   ✅ {method} · {meta['word_count']:,} palabras")
        except Exception as exc:
            msg = str(exc)
            atomic_json(folder / "metadata.json", {
                **video, "success": False, "last_error": msg[:6000],
                "completed_at_utc": now(),
            })
            print("   ❌", msg[:1200])
            try:
                parsed = json.loads(msg)
            except Exception:
                parsed = {}
            if parsed.get("blocked"):
                print("\n🛑 YouTube está bloqueando también esta conexión. Paro para no insistir.")
                break
        time.sleep(args.sleep)

    progress = []
    for v in manifest:
        folder = videos_root / v["video_id"]
        tp = folder / "transcript.txt"
        mp = folder / "metadata.json"
        meta = {}
        if mp.exists():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
            except Exception:
                pass
        progress.append({
            "video_id": v["video_id"], "title": v.get("title"),
            "success": tp.exists() and tp.stat().st_size > 100,
            "method": meta.get("method"), "word_count": meta.get("word_count"),
            "last_error": meta.get("last_error"),
        })
    atomic_json(root / "progress.json", {
        "updated_at_utc": now(), "total": len(progress),
        "success_count": sum(x["success"] for x in progress),
        "pending_count": sum(not x["success"] for x in progress),
        "videos": progress,
    })
    print(f"\n✅ Nuevos completados: {done_this_run}")
    print("📁 Estado:", root / "progress.json")


if __name__ == "__main__":
    main()
