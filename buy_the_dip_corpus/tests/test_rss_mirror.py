import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rss_mirror


SAMPLE = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0">
<channel><title>Buy the dip</title>
<item>
<title>Como buscar, analizar e INVERTIR en EMPRESAS | BUY THE DIP PODCAST</title>
<guid>ep1</guid><pubDate>Tue, 27 Sep 2022 10:00:00 +0000</pubDate>
<itunes:duration>01:02:03</itunes:duration>
<enclosure url="https://media.example/ep1.mp3" length="12345" type="audio/mpeg"/>
</item></channel></rss>'''


class MirrorTests(unittest.TestCase):
    def test_parse_feed_and_duration(self):
        rows=rss_mirror.parse_feed(SAMPLE)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["duration_seconds"],3723)
        self.assertEqual(rows[0]["published_date"],"2022-09-27")
        self.assertEqual(rows[0]["audio_url"],"https://media.example/ep1.mp3")

    def test_normalize_removes_channel_suffix(self):
        a=rss_mirror.normalize_title("Cómo buscar, analizar e INVERTIR en EMPRESAS | BUY THE DIP PODCAST")
        b=rss_mirror.normalize_title("Como buscar analizar e invertir en empresas")
        self.assertEqual(a,b)

    def test_unambiguous_match(self):
        episodes=rss_mirror.parse_feed(SAMPLE)
        youtube=[
            {"video_id":"AAA","title":"Cómo buscar, analizar e INVERTIR en EMPRESAS | BUY THE DIP PODCAST","url":"https://youtu.be/AAA","format":"long"},
            {"video_id":"BBB","title":"Nuestra cartera de inversión en septiembre","url":"https://youtu.be/BBB","format":"long"},
        ]
        mapped=rss_mirror.map_episodes(episodes,youtube)
        self.assertEqual(mapped[0]["match_status"],"matched")
        self.assertEqual(mapped[0]["youtube_video_id"],"AAA")


if __name__ == "__main__":
    unittest.main()
