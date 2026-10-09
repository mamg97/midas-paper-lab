import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import semantic_worker as worker

class SemanticWorkerTests(unittest.TestCase):
    def test_methodology_is_processed_before_portfolio(self):
        queue={"videos":[
            {"video_id":"P","category":"portfolio_update","methodology_relevance_score":9},
            {"video_id":"M","category":"methodology","methodology_relevance_score":1},
        ]}
        rss={"episodes":[
            {"youtube_video_id":"P","match_status":"matched","audio_url":"https://example/p.mp3"},
            {"youtube_video_id":"M","match_status":"matched","audio_url":"https://example/m.mp3"},
        ]}
        selected=worker.choose_next(queue,rss,set())
        self.assertEqual(selected["queue"]["video_id"],"M")

    def test_reviewed_episode_is_skipped(self):
        queue={"videos":[
            {"video_id":"A","category":"methodology","methodology_relevance_score":10},
            {"video_id":"B","category":"methodology","methodology_relevance_score":9},
        ]}
        rss={"episodes":[
            {"youtube_video_id":"A","match_status":"matched","audio_url":"https://example/a.mp3"},
            {"youtube_video_id":"B","match_status":"matched","audio_url":"https://example/b.mp3"},
        ]}
        selected=worker.choose_next(queue,rss,{"A"})
        self.assertEqual(selected["queue"]["video_id"],"B")

    def test_unmatched_audio_is_never_selected(self):
        queue={"videos":[{"video_id":"A","category":"methodology","methodology_relevance_score":10}]}
        rss={"episodes":[{"youtube_video_id":"A","match_status":"unmatched_or_ambiguous","audio_url":"https://example/a.mp3"}]}
        self.assertIsNone(worker.choose_next(queue,rss,set()))

    def test_chunking_preserves_all_lines(self):
        text="\n".join(f"[00:00:{i:02d}] palabra {i}" for i in range(30))
        chunks=worker.chunk_transcript(text,max_chars=100)
        self.assertGreater(len(chunks),1)
        self.assertEqual("\n".join(chunks),text)

    def test_semantic_json_uses_grammar_and_recovers_one_invalid_completion(self):
        class Stub:
            def __init__(self):
                self.kwargs = []
            def create_chat_completion(self, **kwargs):
                self.kwargs.append(kwargs)
                body = '{"evidence": [' if len(self.kwargs) == 1 else '{"evidence":[],"chunk_summary":"Validado"}'
                return {"choices":[{"message":{"content":body}}]}
        llm=Stub()
        result=worker.chat_json(llm,"Extrae solo evidencia","Texto fuente",1600)
        self.assertEqual(result["evidence"],[])
        self.assertEqual(len(llm.kwargs),2)
        self.assertTrue(all(call["response_format"] == {"type":"json_object"} for call in llm.kwargs))
        self.assertEqual(llm.kwargs[1]["temperature"],0)

    def test_semantic_json_rejects_twice_invalid_without_partial_evidence(self):
        class Broken:
            def create_chat_completion(self, **kwargs):
                return {"choices":[{"message":{"content":'{"evidence": ['}}]}
        with self.assertRaisesRegex(ValueError,"llm_invalid_json_after_retry"):
            worker.chat_json(Broken(),"Solo la fuente","Datos",1600)

    def test_publisher_configures_identity_before_rebase(self):
        workflow = (ROOT.parent / ".github/workflows/buy_the_dip_semantic.yml").read_text()
        publisher = workflow.split("- name: Commit semantic evidence", 1)[1]
        self.assertLess(publisher.index("git config user.name"), publisher.index("git commit"))
        self.assertLess(publisher.index("git config user.email"), publisher.index("git pull --rebase"))
        self.assertLess(publisher.index("git commit"), publisher.index("git pull --rebase"))
        self.assertIn("git push", publisher)

    def test_sanitizer_removes_verbatim_fields(self):
        value={"summary":"ok","transcript":"secret","nested":{"quote":"literal","rule":"keep"}}
        clean=worker.sanitize(value)
        self.assertNotIn("transcript",clean)
        self.assertNotIn("quote",clean["nested"])
        self.assertEqual(clean["nested"]["rule"],"keep")

if __name__=="__main__":
    unittest.main()
