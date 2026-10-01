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

    def test_sanitizer_removes_verbatim_fields(self):
        value={"summary":"ok","transcript":"secret","nested":{"quote":"literal","rule":"keep"}}
        clean=worker.sanitize(value)
        self.assertNotIn("transcript",clean)
        self.assertNotIn("quote",clean["nested"])
        self.assertEqual(clean["nested"]["rule"],"keep")

if __name__=="__main__":
    unittest.main()
