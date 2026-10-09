"""Process one Buy The Dip episode into structured strategy evidence.

Audio and transcript text are temporary. Git stores only derived paraphrases and
provenance. YouTube remains the canonical source identity; the official podcast
feed is only a transport fallback for matched long-form episodes.
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, re, tempfile, urllib.request
from pathlib import Path

PRIORITY={"methodology":0,"portfolio_update":1,"sector_theme":2,"company_or_theme":3,
          "macro_market":4,"guest_interview":5,"short":6}
LLM_REPO="Qwen/Qwen3-4B-GGUF"
LLM_FILE="Qwen3-4B-Q4_K_M.gguf"
ASR_MODEL="small"

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def atomic_json(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def reviewed_ids(root):
    root=Path(root)
    return {p.stem for p in root.glob("*.json")} if root.exists() else set()

def rss_by_video(rss):
    out={}
    for row in rss.get("episodes") or []:
        vid=row.get("youtube_video_id")
        if vid and row.get("match_status")=="matched" and row.get("audio_url"):
            out.setdefault(vid,row)
    return out

def choose_next(queue,rss,reviewed):
    mirror=rss_by_video(rss); candidates=[]
    for row in queue.get("videos") or []:
        vid=row.get("video_id")
        if not vid or vid in reviewed or vid not in mirror: continue
        candidates.append((PRIORITY.get(row.get("category"),99),
                           -float(row.get("methodology_relevance_score") or 0),
                           vid,row,mirror[vid]))
    if not candidates: return None
    *_,q,r=sorted(candidates,key=lambda x:x[:3])[0]
    return {"queue":q,"rss":r}

def download(url,destination,max_bytes=300_000_000):
    req=urllib.request.Request(url,headers={"User-Agent":"MIDAS-BuyTheDip/1.0"})
    total=0
    with urllib.request.urlopen(req,timeout=90) as response, open(destination,"wb") as stream:
        length=response.headers.get("Content-Length")
        if length and int(length)>max_bytes: raise ValueError("audio_too_large")
        while True:
            chunk=response.read(1024*1024)
            if not chunk: break
            total+=len(chunk)
            if total>max_bytes: raise ValueError("audio_too_large")
            stream.write(chunk)
    if total<1024: raise ValueError("audio_download_empty")
    return total

def stamp(seconds):
    seconds=max(0,int(seconds or 0)); h,rem=divmod(seconds,3600); m,s=divmod(rem,60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def transcribe(audio_path,model_name=ASR_MODEL):
    from faster_whisper import WhisperModel
    model=WhisperModel(model_name,device="cpu",compute_type="int8",cpu_threads=4)
    segments,info=model.transcribe(str(audio_path),language="es",beam_size=3,
                                   vad_filter=True,condition_on_previous_text=True)
    lines=[]; words=0
    for seg in segments:
        text=re.sub(r"\s+"," ",seg.text or "").strip()
        if not text: continue
        words+=len(text.split()); lines.append(f"[{stamp(seg.start)}] {text}")
    if words<100: raise ValueError("transcription_too_short")
    return "\n".join(lines),{
        "language":getattr(info,"language","es"),
        "language_probability":float(getattr(info,"language_probability",0) or 0),
        "duration_seconds":float(getattr(info,"duration",0) or 0),
        "word_count":words,"segment_count":len(lines),"model":model_name}

def chunk_transcript(text,max_chars=11000):
    chunks=[]; current=[]; size=0
    for line in text.splitlines():
        extra=len(line)+1
        if current and size+extra>max_chars:
            chunks.append("\n".join(current)); current=[]; size=0
        current.append(line); size+=extra
    if current: chunks.append("\n".join(current))
    return chunks

def json_object(text):
    text=str(text or "").strip()
    try:
        value=json.loads(text)
        if isinstance(value,dict): return value
    except json.JSONDecodeError: pass
    start=text.find("{"); end=text.rfind("}")
    if start>=0 and end>start:
        value=json.loads(text[start:end+1])
        if isinstance(value,dict): return value
    raise ValueError("llm_invalid_json")

def load_llm(repo_id=LLM_REPO,filename=LLM_FILE):
    from huggingface_hub import hf_hub_download
    from llama_cpp import Llama
    path=hf_hub_download(repo_id=repo_id,filename=filename)
    return Llama(model_path=path,n_ctx=16384,n_threads=4,n_batch=256,verbose=False)

def chat_json(llm,system,prompt,max_tokens):
    """Bounded retry for truncated/invalid LLM output; never fabricate evidence."""
    for attempt in range(2):
        brevity = ("\nMantén la salida breve (máximo 5 evidencias). "
                   "Conserva solo hechos sustentados. Cierra todo el JSON."
                   if attempt else "")
        response=llm.create_chat_completion(
            messages=[{"role":"system","content":system+brevity+"\n/no_think"},
                      {"role":"user","content":prompt+"\n/no_think"}],
            temperature=0.1 if attempt == 0 else 0,
            max_tokens=max_tokens,
            response_format={"type":"json_object"})
        try:
            return json_object(response["choices"][0]["message"]["content"])
        except (ValueError,json.JSONDecodeError):
            if attempt == 1:
                raise ValueError("llm_invalid_json_after_retry") from None

def sanitize(value):
    if isinstance(value,dict):
        return {k:sanitize(v) for k,v in value.items()
                if k.lower() not in {"transcript","transcription","verbatim","full_text","quote"}}
    if isinstance(value,list): return [sanitize(x) for x in value[:120]]
    if isinstance(value,str): return re.sub(r"\s+"," ",value).strip()[:1800]
    return value

CHUNK_SYSTEM="""Eres un analista de procesos de inversión. Usa solo el fragmento dado.
No inventes ni uses conocimientos externos. No copies frases largas; parafrasea.
Si no puedes atribuir una idea con seguridad a los hosts, usa scope uncertain_or_guest.
Devuelve solo JSON válido."""

CHUNK_PROMPT="""Extrae evidencia para reconstruir una estrategia. Devuelve:
{"evidence":[{"stage":"idea_generation|quality|balance_sheet|valuation|cycle_macro|entry|sizing|add_hold|exit|risk|technical|management|mistake|other","paraphrase":"máximo 350 caracteres","timestamp":"HH:MM:SS o null","scope":"hosts|uncertain_or_guest","confidence":0.0,"automation_hint":"proxy observable o null"}],"named_examples":[],"chunk_summary":"máximo 700 caracteres"}
FRAGMENTO:
"""

FINAL_SYSTEM="""Eres un analista cuantitativo auditando el método de Buy The Dip.
Usa solo evidencia parafraseada del episodio. Distingue proceso, opinión coyuntural,
ejemplo concreto e idea de invitado. Una sola mención nunca basta para regla canónica.
No cites literalmente. Devuelve solo JSON válido."""

FINAL_TEMPLATE="""Sintetiza el episodio para cruzarlo después con cientos de vídeos. Devuelve:
{"episode_summary":"máximo 1400 caracteres","process":{"idea_generation":[],"quality":[],"balance_sheet":[],"valuation":[],"cycle_macro":[],"entry":[],"sizing":[],"add_hold":[],"exit":[],"risk":[],"technical":[],"management":[],"mistakes":[]},"candidate_rules":[{"rule":"paráfrasis compacta","scope":"hosts|uncertain_or_guest","confidence":0.0,"evidence_timestamps":[],"automation_proxy":"variable/cálculo posible o null","cross_video_confirmation_required":true}],"contradictions_or_uncertainties":[],"named_examples":[],"automation_readiness":"low|medium|high"}
METADATOS:
__META__
EVIDENCIA:
__EVIDENCE__
"""

def analyze_episode(llm,transcript,metadata):
    derived=[]
    for idx,chunk in enumerate(chunk_transcript(transcript),1):
        result=chat_json(llm,CHUNK_SYSTEM,CHUNK_PROMPT+chunk,1600)
        derived.append({"chunk":idx,**sanitize(result)})
    prompt=FINAL_TEMPLATE.replace("__META__",json.dumps(metadata,ensure_ascii=False))
    prompt=prompt.replace("__EVIDENCE__",json.dumps(derived,ensure_ascii=False))
    final=chat_json(llm,FINAL_SYSTEM,prompt,2600)
    return sanitize(final),derived

def update_progress(state_dir,queue,rss):
    reviews=reviewed_ids(Path(state_dir)/"reviews"); mirror=rss_by_video(rss)
    ids=[x.get("video_id") for x in queue.get("videos") or [] if x.get("video_id")]
    eligible=[x for x in ids if x in mirror]
    progress={"schema_version":1,"updated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
              "youtube_catalog_count":len(ids),"official_podcast_matched_count":len(eligible),
              "reviewed_count":len(reviews),
              "reviewed_official_podcast_count":sum(x in mirror for x in reviews),
              "remaining_official_podcast_count":sum(x not in reviews for x in eligible),
              "coverage_note":"Official-podcast matches use local ASR; YouTube-only items remain queued."}
    atomic_json(Path(state_dir)/"semantic_progress.json",progress); return progress

def run(queue_path,rss_path,state_dir,asr_model=ASR_MODEL):
    queue=read_json(queue_path); rss=read_json(rss_path); state_dir=Path(state_dir)
    selected=choose_next(queue,rss,reviewed_ids(state_dir/"reviews"))
    if selected is None:
        return {"status":"nothing_pending","progress":update_progress(state_dir,queue,rss)}
    q=selected["queue"]; ep=selected["rss"]; vid=q["video_id"]
    meta={"video_id":vid,"youtube_url":q.get("url"),"title":q.get("title"),
          "category":q.get("category"),"guest_likely":bool(q.get("guest_likely")),
          "podcast_guid":ep.get("guid"),"published_date":ep.get("published_date"),
          "source":"official_podcast_mirror","match_score":ep.get("match_score")}
    with tempfile.TemporaryDirectory(prefix="btd-analysis-") as tmp:
        audio=Path(tmp)/"episode.mp3"; audio_bytes=download(ep["audio_url"],audio)
        transcript,asr=transcribe(audio,asr_model)
        llm=load_llm(os.environ.get("BTD_LLM_REPO",LLM_REPO),
                     os.environ.get("BTD_LLM_FILE",LLM_FILE))
        analysis,evidence=analyze_episode(llm,transcript,meta)
    review={"schema_version":1,"status":"machine_first_pass",
            "reviewed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_identity":"Buy The Dip YouTube channel",
            "transport":{"kind":"official_podcast_mirror","provider":rss.get("provider"),
                         "guid":ep.get("guid"),"published_date":ep.get("published_date"),
                         "youtube_video_id":vid,"match_score":ep.get("match_score"),
                         "audio_bytes_processed_transiently":audio_bytes},
            "models":{"asr":asr,"semantic":{"repo":os.environ.get("BTD_LLM_REPO",LLM_REPO),
                                            "file":os.environ.get("BTD_LLM_FILE",LLM_FILE)}},
            "metadata":meta,"analysis":analysis,"chunk_evidence":evidence,
            "copyright_note":"No audio or verbatim transcript is persisted; only derived paraphrases."}
    atomic_json(state_dir/"reviews"/f"{vid}.json",review)
    return {"status":"reviewed","video_id":vid,"title":q.get("title"),
            "category":q.get("category"),"progress":update_progress(state_dir,queue,rss)}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--queue",required=True)
    p.add_argument("--rss",required=True); p.add_argument("--state",required=True)
    p.add_argument("--asr-model",default=os.environ.get("BTD_ASR_MODEL",ASR_MODEL))
    a=p.parse_args(argv); print(json.dumps(run(a.queue,a.rss,a.state,a.asr_model),
                                           indent=2,ensure_ascii=False))

if __name__=="__main__": main()
