import json
import unittest
from unittest import mock

from reach.channels import arxiv, github, hn, pantip, reddit, rss, search, social, web, youtube, ytdlp
from reach.errors import ReachError
from reach.model import Options

from .helpers import fake_http

PANTIP_HTML = """<html><head><title>ทดสอบกระทู้ - Pantip</title>
<meta property="og:title" content="ทดสอบกระทู้"></head><body>
<a href="https://pantip.com/tag/ทดสอบ">ทดสอบ</a>
<div class="display-post-story-wrapper"><div class="display-post-story">
เนื้อหา<br/>บรรทัดสอง <div class="inner">ซ้อน</div> จบ</div></div>
<div class="display-post-story-footer"><span class="like-score ">7</span></div>
<a class="display-post-name owner" id="1" href="/profile/1">เจ้าของ</a>
<span data-utime="10/20/2026 08:18:37"></span>
<div class="display-post-story">{{:template}}</div>
</body></html>"""


def pantip_comment(no, msg, point, replies=(), reply_count=None):
    return {
        "comment_no": no, "message": msg, "point": point, "created_time": "1760000000",
        "data_ip_email": "1.2.3.4", "user": {"name": f"user{no}", "mid": 1},
        "replies": [{"message": r, "point": 1, "data_utime": "10/20/2026 09:00:00",
                     "user": {"name": "rep"}, "ipv6": "secret"} for r in replies],
        "reply_count": reply_count if reply_count is not None else len(replies),
    }


class Pantip(unittest.TestCase):
    def test_match(self):
        self.assertTrue(pantip.match("https://pantip.com/topic/44262560"))
        self.assertFalse(pantip.match("https://pantip.com/forum/chalermthai"))

    def test_topic_and_comments(self):
        page = {"count": 3, "comments": [
            pantip_comment(1, "แรก<br />\nต่อ&nbsp;", 1),
            pantip_comment(2, "ฮิต", 10, replies=["ตอบ"], reply_count=8),
            pantip_comment(3, "กลาง", 5),
        ]}
        with fake_http([("render_comments", page), ("pantip.com/topic/", PANTIP_HTML)]) as calls:
            r = pantip.read("https://pantip.com/topic/123?x=1", Options(comments=True, limit=2))
        self.assertEqual(r.title, "ทดสอบกระทู้")
        self.assertEqual(r.author, "เจ้าของ")
        self.assertEqual(r.published, "2026-10-20T08:18:37+07:00")
        self.assertIn("บรรทัดสอง", r.text)
        self.assertIn("ซ้อน", r.text)
        self.assertNotIn("template", r.text)
        self.assertEqual(r.stats["likes"], 7)
        self.assertEqual([c.text for c in r.comments], ["ฮิต", "กลาง"])  # sorted by points, limited
        self.assertEqual(r.comments[0].replies[0].text, "ตอบ")
        self.assertTrue(any("7 older replies" in w for w in r.warnings))
        dumped = json.dumps(r.to_dict(), ensure_ascii=False)
        self.assertNotIn("1.2.3.4", dumped)
        self.assertNotIn("secret", dumped)
        self.assertIn("X-Requested-With", calls[1][1]["headers"])

    def test_paging(self):
        pages = {1: {"count": 150, "comments": [pantip_comment(i, f"c{i}", 0) for i in range(1, 101)]},
                 2: {"count": 150, "comments": [pantip_comment(i, f"c{i}", 0) for i in range(101, 151)]}}
        with fake_http([("page=2", pages[2]), ("page=1", pages[1]), ("pantip.com/topic/", PANTIP_HTML)]):
            r = pantip.read("https://pantip.com/topic/1", Options(comments=True, limit=500, sort="new"))
        self.assertEqual(len(r.comments), 150)
        self.assertEqual(r.comments[0].text, "c150")


class YouTube(unittest.TestCase):
    RAW = [
        {"id": "a", "parent": "root", "text": "low", "like_count": 1, "author": "A", "timestamp": 1700000000},
        {"id": "b", "parent": "root", "text": "high", "like_count": 99, "author": "B", "timestamp": 1600000000},
        {"id": "b.1", "parent": "b", "text": "reply", "like_count": 3, "author": "C", "timestamp": 1650000000},
    ]

    def test_tree_top(self):
        roots = ytdlp.build_tree(self.RAW, Options(sort="top", limit=5))
        self.assertEqual([c.text for c in roots], ["high", "low"])
        self.assertEqual(roots[0].replies[0].text, "reply")
        self.assertEqual(roots[0].published, "2020-09-13")

    def test_tree_new_and_depth(self):
        roots = ytdlp.build_tree(self.RAW, Options(sort="new", depth=1, limit=1))
        self.assertEqual([c.text for c in roots], ["low"])
        self.assertEqual(roots[0].replies, [])

    def test_comment_count_not_confused_with_fetched(self):
        data = {"title": "t", "comment_count": 2, "comments": self.RAW[:2]}
        r = ytdlp.to_result(data, "youtube", "u", Options(comments=True))
        self.assertIsNone(r.stats["comments"])
        self.assertEqual(r.stats["comments_fetched"], 2)

    def test_blocked_comments_warn(self):
        r = ytdlp.to_result({"title": "t", "comment_count": 50, "comments": []}, "tiktok", "u", Options(comments=True))
        self.assertEqual(r.comments, [])
        self.assertTrue(any("returned none" in w for w in r.warnings))

    def test_pick_manual_first(self):
        data = {"language": "th", "subtitles": {"th": [{}], "en": [{}]}, "automatic_captions": {"th-orig": [{}]}}
        self.assertEqual(youtube.pick_track(data, [])[:2], ("manual", "th"))
        self.assertEqual(youtube.pick_track(data, ["en"])[:2], ("manual", "en"))

    def test_pick_auto_is_flagged(self):
        data = {"language": "en", "subtitles": {}, "automatic_captions": {"en-orig": [{}], "en": [{}], "th": [{}]}}
        kind, key, w = youtube.pick_track(data, [])
        self.assertEqual((kind, key), ("auto", "en-orig"))
        self.assertTrue(w and "auto-generated" in w[0])
        kind, key, w = youtube.pick_track(data, ["th"])
        self.assertEqual((kind, key), ("auto", "th"))
        self.assertIn("MACHINE-TRANSLATED", w[0])

    def test_pick_none(self):
        with self.assertRaises(ReachError) as cm:
            youtube.pick_track({"subtitles": {}, "automatic_captions": {}}, [])
        self.assertEqual(cm.exception.code, "not_found")

    def test_json3(self):
        payload = {"events": [{"segs": [{"utf8": "hello\nworld"}]}, {"segs": [{"utf8": "hello world"}]},
                              {"tStartMs": 1}, {"segs": [{"utf8": "bye"}]}]}
        self.assertEqual(youtube.json3_to_text(payload), "hello world\nbye")

    def test_comment_extractor_args(self):
        self.assertEqual(youtube._comment_args(Options(limit=10, sort="new")),
                         "youtube:max_comments=all,10,50,5;comment_sort=new")


class Social(unittest.TestCase):
    def test_platforms(self):
        self.assertEqual(social.platform_of("https://twitter.com/a/status/1"), "x")
        self.assertEqual(social.platform_of("https://vm.tiktok.com/x"), "tiktok")
        self.assertEqual(social.platform_of("https://fb.watch/abc"), "facebook")
        self.assertIsNone(social.platform_of("https://notx.com/a"))

    def test_x_embed(self):
        data = {"__typename": "Tweet", "id_str": "20", "text": "hi", "favorite_count": 5, "conversation_count": 2,
                "created_at": "2006-03-21T20:50:14.000Z", "user": {"name": "jack", "screen_name": "jack"},
                "mediaDetails": [{"media_url_https": "https://pbs.twimg.com/x.jpg"}]}
        with fake_http([("syndication", data)]):
            r = social.read("https://x.com/jack/status/20?s=1", Options(comments=True))
        self.assertEqual(r.author, "@jack")
        self.assertIn("pbs.twimg.com", r.text)
        self.assertEqual(r.comments, [])
        self.assertTrue(any("replies cannot be read" in w for w in r.warnings))

    def test_x_tombstone(self):
        with self.assertRaises(ReachError):
            social.parse_x_syndication({"__typename": "TweetTombstone"}, "u")

    def test_fallback_chain_reports_everything(self):
        with fake_http([("syndication", ReachError("blocked", "x said no")),
                        ("r.jina.ai", ReachError("blocked", "jina said no"))]), \
                mock.patch("reach.proc.run_tool", side_effect=ReachError("tool_missing", "yt-dlp missing")):
            with self.assertRaises(ReachError) as cm:
                social.read("https://x.com/a/status/1", Options())
        self.assertEqual(len(cm.exception.tried), 3)
        self.assertIn("cookies-from-browser", cm.exception.hint)


class Reddit(unittest.TestCase):
    POST = [
        {"data": {"children": [{"data": {"title": "T", "author": "op", "selftext": "body", "score": 10,
                                         "num_comments": 2, "permalink": "/r/x/comments/1/t/", "created_utc": 0}}]}},
        {"data": {"children": [
            {"kind": "t1", "data": {"author": "a", "body": "c1", "score": 5, "created_utc": 0,
                                    "replies": {"data": {"children": [{"kind": "t1", "data": {"author": "b", "body": "r1", "score": 1, "replies": ""}}]}}}},
            {"kind": "more", "data": {}},
        ]}},
    ]

    def test_paths(self):
        self.assertEqual(reddit._path("https://redd.it/abc"), "/comments/abc")
        self.assertEqual(reddit._path("https://www.reddit.com/r/x/comments/1/t/.json"), "/r/x/comments/1/t")

    def test_post_with_comments(self):
        with fake_http([("www.reddit.com", self.POST)]):
            r = reddit.read("https://www.reddit.com/r/x/comments/1/t/", Options(comments=True))
        self.assertEqual(r.title, "T")
        self.assertEqual(r.comments[0].replies[0].text, "r1")
        self.assertEqual(len(r.comments), 1)

    def test_blocked_without_app_gives_hint(self):
        with fake_http([("www.reddit.com", ReachError("blocked", "403"))]), mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ReachError) as cm:
                reddit.read("https://www.reddit.com/r/x/", Options())
        self.assertIn("REDDIT_CLIENT_ID", cm.exception.hint)

    def test_app_only_oauth_fallback(self):
        reddit._token = None
        env = {"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "sec"}
        with fake_http([("access_token", {"access_token": "tok"}), ("oauth.reddit.com", self.POST),
                        ("www.reddit.com", ReachError("blocked", "403"))]) as calls, \
                mock.patch.dict("os.environ", env):
            r = reddit.read("https://www.reddit.com/r/x/comments/1/t/", Options())
        reddit._token = None
        self.assertEqual(r.source, "reddit api (app-only oauth)")
        self.assertEqual(calls[-1][1]["headers"]["Authorization"], "Bearer tok")


class GitHub(unittest.TestCase):
    def test_dotdot_refused(self):
        with self.assertRaises(ReachError):
            github.read("https://github.com/../..", Options())

    def test_issue_with_comments_public_api(self):
        issue = {"html_url": "https://github.com/o/r/issues/1", "title": "Bug", "body": "b", "user": {"login": "u"},
                 "state": "open", "comments": 2, "reactions": {"total_count": 1}}
        comments = [{"user": {"login": "a"}, "body": "x", "reactions": {"total_count": 0}},
                    {"user": {"login": "b"}, "body": "y", "reactions": {"total_count": 9}}]
        with mock.patch("reach.proc.which", return_value=None), \
                fake_http([("/comments", comments), ("/issues/1", issue)]):
            r = github.read("https://github.com/o/r/issues/1", Options(comments=True))
        self.assertEqual(r.title, "#1 Bug")
        self.assertEqual([c.author for c in r.comments], ["b", "a"])


class HN(unittest.TestCase):
    def test_item_tree(self):
        item = {"id": 1, "title": "T", "author": "pg", "url": "http://x", "points": 3, "children": [
            {"type": "comment", "author": "a", "text": "<p>hi &amp; bye</p>", "created_at": "1", "children": [
                {"type": "comment", "author": "b", "text": "deep", "created_at": "2", "children": []}]},
            {"type": "comment", "author": None, "text": None, "children": []},
        ]}
        r = hn.parse_item(item, Options(comments=True, depth=1))
        self.assertEqual(r.comments[0].text, "hi & bye")
        self.assertEqual(r.comments[0].replies, [])
        self.assertEqual(len(r.comments), 1)


ARXIV = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/1706.03762v7</id><title>Attention
 Is All You Need</title><summary> abs </summary><published>2017-06-12T17:57:34Z</published>
<author><name>A</name></author><author><name>B</name></author></entry></feed>"""


class Arxiv(unittest.TestCase):
    def test_parse(self):
        it = arxiv.parse_feed(ARXIV)[0]
        self.assertEqual(it.title, "Attention Is All You Need")
        self.assertEqual(it.author, "A, B")
        self.assertTrue(it.url.startswith("https://"))

    def test_match(self):
        self.assertTrue(arxiv.match("https://arxiv.org/pdf/1706.03762v7.pdf"))
        self.assertEqual(arxiv.ID_RE.search("/abs/1706.03762v7").group(1), "1706.03762")


class RSS(unittest.TestCase):
    def test_rss2(self):
        xml = """<rss><channel><title>F</title><item><title>A</title><link>https://a</link>
        <description>&lt;b&gt;x&lt;/b&gt;</description><pubDate>d</pubDate></item></channel></rss>"""
        r = rss.parse(xml, "u", 10)
        self.assertEqual((r.title, r.items[0].title, r.items[0].snippet), ("F", "A", "x"))

    def test_atom(self):
        xml = """<feed xmlns="http://www.w3.org/2005/Atom"><title>F</title><entry><title>A</title>
        <link rel="alternate" href="https://a"/><updated>u</updated></entry></feed>"""
        self.assertEqual(rss.parse(xml, "u", 10).items[0].url, "https://a")

    def test_entities_refused(self):
        with self.assertRaises(ReachError):
            rss.parse('<!DOCTYPE x [<!ENTITY a "aaaa">]><rss/>', "u", 10)


class Search(unittest.TestCase):
    DDG = """<div class="result results_links"><a rel="nofollow" class="result__a"
    href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpantip.com%2F&amp;rut=1">Pantip <b>Home</b></a>
    <a class="result__snippet" href="x">snippet <b>text</b></a></div>
    <a class="result__a" href="https://duckduckgo.com/y.js?ad=1">ad</a>"""

    def test_ddg_parse(self):
        items = search.parse_ddg(self.DDG)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://pantip.com/")
        self.assertEqual(items[0].title, "Pantip Home")
        self.assertEqual(items[0].snippet, "snippet text")

    def test_ddg_blocked(self):
        with self.assertRaises(ReachError):
            search.parse_ddg("<html>anomaly detected</html>")

    def test_keyless_failure_hint(self):
        with fake_http([("duckduckgo", "anomaly")]), mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ReachError) as cm:
                search.search("q", Options())
        self.assertIn("BRAVE_API_KEY", cm.exception.hint)

    def test_brave_preferred(self):
        data = {"web": {"results": [{"title": "T", "url": "https://t", "description": "<strong>d</strong>"}]}}
        with fake_http([("api.search.brave.com", data)]) as calls, mock.patch.dict("os.environ", {"BRAVE_API_KEY": "k"}):
            r = search.search("q", Options())
        self.assertEqual((r.source, r.items[0].snippet), ("brave", "d"))
        self.assertEqual(calls[0][1]["headers"]["X-Subscription-Token"], "k")


class Web(unittest.TestCase):
    def test_jina_parse(self):
        r = web.parse_jina("Title: Hello\nURL Source: u\nPublished Time: t\n\nMarkdown Content:\nbody", "u")
        self.assertEqual((r.title, r.published, r.text), ("Hello", "t", "body"))

    def test_jina_challenge_detected(self):
        with self.assertRaises(ReachError):
            web.parse_jina("Title: Just a moment...\n\nMarkdown Content:\nx", "u")

    def test_direct_fallback(self):
        html = "<html><title>P</title><script>evil()</script><h1>Head</h1><p>Para</p></html>"
        with mock.patch("reach.net.check_url", side_effect=lambda u: u), \
                fake_http([("r.jina.ai", ReachError("blocked", "no")), ("example.org", html)]):
            r = web.read("https://example.org/", Options())
        self.assertEqual(r.title, "P")
        self.assertIn("# Head", r.text)
        self.assertNotIn("evil", r.text)
        self.assertTrue(r.warnings)

    def test_no_jina_env(self):
        with mock.patch.dict("os.environ", {"REACH_NO_JINA": "1"}):
            self.assertFalse(web.jina_enabled())


if __name__ == "__main__":
    unittest.main()
