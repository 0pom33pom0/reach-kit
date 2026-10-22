"""Real network tests. Not run by default: REACH_LIVE=1 python -m unittest tests.test_live"""

import os
import unittest

from reach import core
from reach.errors import ReachError
from reach.model import Options

LIVE = os.environ.get("REACH_LIVE") == "1"


@unittest.skipUnless(LIVE, "set REACH_LIVE=1 to hit the real platforms")
class Live(unittest.TestCase):
    def opts(self, **kw):
        o = Options(no_cache=True, limit=3)
        for k, v in kw.items():
            setattr(o, k, v)
        return o

    def test_web(self):
        self.assertIn("Example", core.read("https://example.com", self.opts()).title)

    def test_pantip_comments(self):
        r = core.comments("https://pantip.com/topic/43000000", self.opts())
        self.assertTrue(r.comments)

    def test_youtube(self):
        r = core.comments("https://www.youtube.com/watch?v=jNQXAC9IVRw", self.opts())
        self.assertTrue(r.comments)
        t = core.transcript("https://www.youtube.com/watch?v=jNQXAC9IVRw", self.opts())
        self.assertIn("elephants", t.text)

    def test_x(self):
        self.assertIn("twttr", core.read("https://x.com/jack/status/20", self.opts()).text)

    def test_hn_arxiv(self):
        self.assertTrue(core.comments("https://news.ycombinator.com/item?id=1", self.opts()).comments)
        self.assertIn("Attention", core.read("https://arxiv.org/abs/1706.03762", self.opts()).title)

    def test_reddit_reports_clearly(self):
        try:
            core.read("https://www.reddit.com/r/announcements/", self.opts())
        except ReachError as e:
            self.assertIn(e.code, ("blocked", "login_required"))
            self.assertTrue(e.hint)


if __name__ == "__main__":
    unittest.main()
