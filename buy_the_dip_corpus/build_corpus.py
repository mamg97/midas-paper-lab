"""Build a source-pure, non-verbatim corpus map for Buy The Dip.

Captions are downloaded into a temporary directory and destroyed at process end.
Only derived statistics are committed. This is a screening layer; semantic
per-video review remains a separate human/LLM step before freezing a trading rule.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import numpy as np
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer


SURFACES = {
    "long": "videos",
    "live": "streams",
    "short": "shorts",
}

STOPWORDS_ES = {
    "a","al","algo","algunas","algunos","ante","antes","como","con","contra","cual",
    "cuando","de","del","desde","donde","dos","el","ella","ellas","ellos","en","entre",
    "era","erais","eran","eras","eres","es","esa","esas","ese","eso","esos","esta",
    "estaba","estaban","estado","estais","estamos","estan","estar","estas","este","esto",
    "estos","fue","fueron","ha","hace","hacia","han","hasta","hay","la","las","le","les",
    "lo","los","mas","me","mi","mis","mucho","muy","no","nos","o","os","otra","otro",
    "para","pero","poco","por","porque","que","qué","se","si","sí","sin","sobre","son",
    "su","sus","tambien","también","te","tener","tiene","todo","tu","tus","un","una",
    "uno","unos","y","ya","yo","vamos","bueno","pues","vale","aqui","aquí","ahora",
    "entonces","creo","puede","pueden","ser","hacer","ver","tema","cosas","cosa"
}


def _run(cmd, *, timeout=1200):
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-20:])
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd[:3])}\n{tail}")
    return proc.stdout


def _norm(text):
    text = html.unescape(str(text or "")).lower()
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _iso_date(entry):
    value = entry.get("timestamp") or entry.get("release_timestamp")
    if isinstance(value, (int, float)) and value > 0:
        return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).date().isoformat()
    upload = str(entry.get("upload_date") or "")
    if re.fullmatch(r"\d{8}", upload):
        return f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}"
    return None


def _flat_surface(channel_url, suffix):
    url = channel_url.rstrip("/") + "/" + suffix
    payload = _run([
        "yt-dlp", "--flat-playlist", "--dump-single-json",
        "--ignore-errors", "--no-warnings", url
    ])
    raw = json.loads(payload)
    return raw.get("entries") or []


def build_manifest(config):
    wanted = set(config.get("include_formats") or SURFACES)
    merged = {}
    for fmt, suffix in SURFACES.items():
        if fmt not in wanted:
            continue
        for item in _flat_surface(config["channel_url"], suffix):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            video_id = str(item["id"])
            row = merged.setdefault(video_id, {
                "video_id": video_id,
                "title": item.get("title") or video_id,
                "published_date": _iso_date(item),
                "duration_seconds": item.get("duration"),
                "view_count": item.get("view_count"),
                "surfaces": [],
            })
            if fmt not in row["surfaces"]:
                row["surfaces"].append(fmt)
            for key, value in {
                "title": item.get("title"),
                "published_date": _iso_date(item),
                "duration_seconds": item.get("duration"),
                "view_count": item.get("view_count"),
            }.items():
                if row.get(key) in (None, "", video_id) and value not in (None, ""):
                    row[key] = value
    rows = list(merged.values())
    priority = {"long": 0, "live": 1, "short": 2}
    for row in rows:
        row["format"] = sorted(row["surfaces"], key=lambda x: priority.get(x, 9))[0]
        row["url"] = "https://www.youtube.com/watch?v=" + row["video_id"]
    rows.sort(key=lambda x: ((x["published_date"] or "0000-00-00"), x["video_id"]))
    return rows


def _download_captions(channel_url, temp_dir, languages):
    langs = ",".join(dict.fromkeys(languages + ["es.*", "en.*"]))
    for suffix in SURFACES.values():
        url = channel_url.rstrip("/") + "/" + suffix
        cmd = [
            "yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
            "--sub-langs", langs, "--sub-format", "vtt", "--ignore-errors",
            "--no-warnings", "--sleep-requests", "0.15",
            "-o", str(Path(temp_dir) / "%(id)s.%(language)s.%(ext)s"), url
        ]
        # A surface failure should not destroy the full manifest; coverage is explicit.
        try:
            subprocess.run(cmd, text=True, capture_output=True, timeout=3600)
        except subprocess.TimeoutExpired:
            pass


def _parse_vtt(path):
    lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
    text_lines = []
    previous = None
    for raw in lines:
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        if "-->" in line or re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"<[^>]+>", " ", line)
        line = html.unescape(line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line == previous:
            continue
        text_lines.append(line)
        previous = line
    return " ".join(text_lines)


def _select_caption(video_id, temp_dir, preferred):
    files = list(Path(temp_dir).glob(video_id + ".*.vtt"))
    if not files:
        return None, None
    preferences = [_norm(x).replace("_", "-") for x in preferred]
    scored = []
    for path in files:
        name = path.name[len(video_id)+1:-4]
        lang = _norm(name).replace("_", "-")
        score = 99
        for idx, pref in enumerate(preferences):
            if lang == pref or lang.startswith(pref + "-"):
                score = idx
                break
        scored.append((score, len(lang), path, name))
    _, _, path, lang = sorted(scored, key=lambda x: (x[0], x[1], x[2].name))[0]
    text = _parse_vtt(path)
    return (text or None), lang


def _category(title, fmt):
    t = _norm(title)
    if fmt == "short":
        return "short"
    if any(x in t for x in ["nuestra cartera", "cartera de inversion", "rentabilidad del ano",
                             "resumen del mes", "cartera y resumen"]):
        return "portfolio_update"
    if any(x in t for x in ["como buscar", "como analizar", "concentrar o diversificar",
                             "nuestros fracasos", "hemos aprendido", "analisis tecnico y value"]):
        return "methodology"
    if any(x in t for x in ["por un experto", "con paco", "con diego", "con gabriel",
                             "con albert", "entrevista", "javier accion", "buy&hold"]):
        return "guest_interview"
    if any(x in t for x in ["inflacion", "recesion", "fed", "tipos de interes", "mercado",
                             "bolsa", "aranceles", "empleo"]):
        return "macro_market"
    if any(x in t for x in ["oro", "petroleo", "uranio", "platino", "paladio", "barcos",
                             "energia", "metales", "materias primas", "software", "saas"]):
        return "sector_theme"
    return "company_or_theme"


def _guest_likely(title, category):
    t = _norm(title)
    return category == "guest_interview" or bool(
        re.search(r"\b(con|entrevista a)\b", t)
        and not any(x in t for x in ["con malas", "con mas", "con nuestra"])
    )


def _lexicon_counts(text, lexicons):
    n = _norm(text)
    result = {}
    for group, terms in lexicons.items():
        total = 0
        hits = {}
        for term in terms:
            key = _norm(term)
            count = n.count(key)
            if count:
                hits[term] = count
                total += count
        result[group] = {"count": total, "terms": hits}
    return result


def _relevance(row):
    counts = row["lexicon_counts"]
    weights = {
        "quality": 2.2, "cash_flow": 2.0, "valuation": 2.4, "balance_sheet": 1.5,
        "capital_allocation": 2.0, "contrarian": 2.2, "cyclical": 1.7,
        "portfolio": 2.0, "entry": 1.7, "exit": 2.2, "risk": 2.0,
        "technical": 1.0, "management": 1.5, "macro": 0.35,
    }
    words = max(250, int(row.get("word_count") or 0))
    score = sum(weights[k] * math.log1p(counts[k]["count"] * 1000 / words) for k in weights)
    category_bonus = {
        "methodology": 12.0,
        "portfolio_update": 8.0,
        "sector_theme": 3.0,
        "company_or_theme": 2.0,
        "guest_interview": -2.0,
        "macro_market": -1.0,
        "short": -8.0,
    }
    score += category_bonus.get(row["category"], 0.0)
    if row.get("guest_likely"):
        score -= 3.0
    return round(score, 4)


def _topic_model(rows, texts, config):
    usable = [(i, text) for i, text in enumerate(texts) if len(text.split()) >= 120]
    if len(usable) < 12:
        return [], {}
    indices, docs = zip(*usable)
    stopwords = sorted(STOPWORDS_ES)
    vectorizer = TfidfVectorizer(
        lowercase=True, strip_accents="unicode", stop_words=stopwords,
        ngram_range=(1, 2), min_df=2, max_df=0.90,
        max_features=int(config.get("max_features", 6000))
    )
    matrix = vectorizer.fit_transform(docs)
    components = min(int(config.get("topic_count", 12)), max(2, min(matrix.shape) - 1))
    model = NMF(n_components=components, init="nndsvda", random_state=17, max_iter=500)
    weights = model.fit_transform(matrix)
    terms = np.array(vectorizer.get_feature_names_out())
    topics = []
    for topic_id, component in enumerate(model.components_):
        top = component.argsort()[::-1][:12]
        topics.append({
            "topic_id": topic_id,
            "terms": [str(terms[i]) for i in top],
        })
    video_topics = {}
    for local_idx, row_idx in enumerate(indices):
        order = weights[local_idx].argsort()[::-1][:3]
        video_topics[rows[row_idx]["video_id"]] = [
            {"topic_id": int(i), "weight": round(float(weights[local_idx][i]), 6)}
            for i in order if weights[local_idx][i] > 0
        ]
    return topics, video_topics


def build(config, output):
    manifest = build_manifest(config)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="buy-the-dip-captions-") as temp_dir:
        _download_captions(
            config["channel_url"], temp_dir,
            list(config.get("preferred_caption_languages") or ["es", "en"])
        )
        rows, texts = [], []
        for item in manifest:
            text, lang = _select_caption(
                item["video_id"], temp_dir,
                list(config.get("preferred_caption_languages") or ["es", "en"])
            )
            text = text or ""
            category = _category(item["title"], item["format"])
            counts = _lexicon_counts(text, config["strategy_lexicons"])
            row = {
                **item,
                "caption_available": bool(text),
                "caption_language": lang,
                "word_count": len(text.split()) if text else 0,
                "category": category,
                "guest_likely": _guest_likely(item["title"], category),
                "lexicon_counts": counts,
            }
            row["methodology_relevance_score"] = _relevance(row)
            rows.append(row)
            texts.append(text)

        topics, video_topics = _topic_model(rows, texts, config)
        for row in rows:
            row["topics"] = video_topics.get(row["video_id"], [])

    by_category = collections.Counter(row["category"] for row in rows)
    by_format = collections.Counter(row["format"] for row in rows)
    transcript_rows = [row for row in rows if row["caption_available"]]
    aggregate = {}
    for group in config["strategy_lexicons"]:
        videos = sum(row["lexicon_counts"][group]["count"] > 0 for row in transcript_rows)
        mentions = sum(row["lexicon_counts"][group]["count"] for row in transcript_rows)
        aggregate[group] = {"videos_with_signal": videos, "mentions": mentions}

    report = {
        "schema_version": 1,
        "source_name": config["source_name"],
        "channel_url": config["channel_url"],
        "channel_id": config["channel_id"],
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "config_version": config["version"],
        "manifest_count": len(manifest),
        "by_format": dict(by_format),
        "caption_coverage": {
            "available": len(transcript_rows),
            "missing": len(rows) - len(transcript_rows),
            "pct": round(100 * len(transcript_rows) / len(rows), 2) if rows else 0,
        },
        "by_category": dict(by_category),
        "lexicon_aggregate": aggregate,
        "topics": topics,
        "top_methodology_videos": [
            {
                "video_id": row["video_id"],
                "title": row["title"],
                "published_date": row["published_date"],
                "category": row["category"],
                "guest_likely": row["guest_likely"],
                "score": row["methodology_relevance_score"],
                "url": row["url"],
            }
            for row in sorted(rows, key=lambda x: (-x["methodology_relevance_score"], x["video_id"]))[:40]
        ],
        "methodology_note": (
            "Corpus screening only. No trading rule is considered canonical until semantic "
            "review distinguishes host process from guest opinions and recurring themes."
        ),
    }
    manifest_out = {
        "schema_version": 1,
        "channel_url": config["channel_url"],
        "channel_id": config["channel_id"],
        "source_hash": hashlib.sha256(
            json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "videos": manifest,
    }
    Path(output / "manifest.json").write_text(
        json.dumps(manifest_out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    Path(output / "corpus_features.json").write_text(
        json.dumps({"schema_version": 1, "videos": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    Path(output / "corpus_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        "# Buy The Dip · corpus report", "",
        f"Fuente canónica: {config['channel_url']}", "",
        f"- Vídeos inventariados: **{len(rows)}**",
        f"- Captions utilizables: **{len(transcript_rows)}** ({report['caption_coverage']['pct']:.2f} %)",
        f"- Formatos: **{dict(by_format)}**",
        f"- Categorías derivadas: **{dict(by_category)}**", "",
        "## Señales recurrentes", "",
        "| Señal | Vídeos con señal | Menciones |",
        "| --- | ---: | ---: |",
    ]
    for group, values in sorted(aggregate.items(), key=lambda kv: -kv[1]["videos_with_signal"]):
        lines.append(f"| {group} | {values['videos_with_signal']} | {values['mentions']} |")
    lines += ["", "## Episodios prioritarios para lectura semántica", ""]
    for item in report["top_methodology_videos"][:25]:
        guest = " · invitado probable" if item["guest_likely"] else ""
        lines.append(
            f"- {item['published_date'] or 's/f'} · **{item['title']}** · "
            f"{item['category']} · score {item['score']:.2f}{guest} · {item['url']}"
        )
    lines += ["", "## Topics no supervisados", ""]
    for topic in topics:
        lines.append(f"- Topic {topic['topic_id']}: " + ", ".join(topic["terms"]))
    lines += [
        "", "## Límite metodológico", "",
        "Este informe no guarda transcripciones verbatim y no convierte automáticamente "
        "frecuencia de palabras en reglas de inversión. Sirve para asegurar que el análisis "
        "semántico posterior cubra el canal entero y priorice los episodios que realmente "
        "explican proceso, compras, ventas, errores, calidad, valoración y gestión de riesgo.", ""
    ]
    Path(output / "corpus_report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    report = build(config, args.output)
    print(json.dumps({
        "manifest_count": report["manifest_count"],
        "caption_coverage": report["caption_coverage"],
        "top_methodology": report["top_methodology_videos"][:5],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
