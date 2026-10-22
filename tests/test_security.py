import ast
import re
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

from reach import net, proc
from reach.channels import ytdlp
from reach.errors import ReachError
from reach.model import Options

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "reach"
SOURCES = sorted(PKG.rglob("*.py"))

# Every import must be from this list. Adding one is a reviewed, deliberate change.
STDLIB_ALLOWED = {
    "__future__", "argparse", "ast", "base64", "concurrent", "dataclasses", "datetime", "filecmp",
    "hashlib", "html", "ipaddress", "json", "math", "os", "pathlib", "re", "shutil", "socket",
    "subprocess", "sys", "time", "typing", "urllib", "xml", "zlib",
}


def resolve(host_ips):
    def fake(host, port, proto=0):
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
                for ip in host_ips]
    return mock.patch("socket.getaddrinfo", side_effect=fake)


class SSRFGuard(unittest.TestCase):
    def blocked(self, url, ips=("93.184.216.34",)):
        with resolve(ips):
            with self.assertRaises(ReachError) as cm:
                net.check_url(url)
        return cm.exception.code

    def test_public_ok(self):
        with resolve(["93.184.216.34"]):
            self.assertEqual(net.check_url("https://example.com/a"), "https://example.com/a")

    def test_schemes(self):
        for u in ("file:///etc/passwd", "ftp://example.com", "gopher://x", "javascript:alert(1)"):
            self.assertIn(self.blocked(u), ("unsafe_url", "invalid_url"), u)

    def test_localhost_names(self):
        self.assertEqual(self.blocked("http://localhost:8080"), "unsafe_url")
        self.assertEqual(self.blocked("http://foo.localhost"), "unsafe_url")

    def test_private_and_special_ips(self):
        for ip in ("127.0.0.1", "10.1.2.3", "172.16.0.5", "192.168.1.1", "169.254.169.254",
                   "0.0.0.0", "100.64.0.1", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "224.0.0.1"):
            self.assertEqual(self.blocked("http://evil.example/", (ip,)), "unsafe_url", ip)

    def test_dns_rebinding_any_private_answer(self):
        self.assertEqual(self.blocked("http://evil.example/", ("93.184.216.34", "127.0.0.1")), "unsafe_url")

    def test_redirect_to_private_is_blocked(self):
        handler = net._SafeRedirect()
        with resolve(["127.0.0.1"]):
            with self.assertRaises(ReachError):
                handler.redirect_request(mock.Mock(), None, 302, "Found", {}, "http://internal.example/")

    def test_http_get_checks_before_connecting(self):
        with resolve(["10.0.0.1"]), mock.patch.object(net._opener, "open") as op:
            with self.assertRaises(ReachError):
                net.http_get("http://intranet.example/")
            op.assert_not_called()


class ProcessRules(unittest.TestCase):
    def test_only_allowlisted_tools(self):
        with self.assertRaises(ValueError):
            proc.run_tool("bash", ["-c", "echo hi"])
        with self.assertRaises(ValueError):
            proc.which("curl")

    def test_missing_tool_is_reported(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(ReachError) as cm:
                proc.run_tool("yt-dlp", ["--version"])
        self.assertEqual(cm.exception.code, "tool_missing")

    def test_url_is_never_parsed_as_an_option(self):
        with mock.patch("reach.proc.run_tool", return_value="{}") as rt:
            ytdlp.info("--exec=touch /tmp/pwned", Options())
        args = rt.call_args[0][1]
        self.assertEqual(args[-2:], ["--", "--exec=touch /tmp/pwned"])


class StaticRules(unittest.TestCase):
    def test_no_shell_true_anywhere(self):
        for p in SOURCES:
            self.assertNotRegex(p.read_text(encoding="utf-8"), r"shell\s*=\s*True", p.name)

    def test_subprocess_only_in_proc(self):
        for p in SOURCES:
            if p.name == "proc.py":
                continue
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                    self.assertNotIn("subprocess", names, f"{p.name} imports subprocess")
                    self.assertNotIn("os.system", names)
            self.assertNotRegex(p.read_text(encoding="utf-8"), r"os\.(system|popen|exec)", p.name)

    def test_imports_are_stdlib_allowlist(self):
        for p in SOURCES:
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    tops = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    tops = [(node.module or "").split(".")[0]]
                else:
                    continue
                for t in tops:
                    self.assertIn(t, STDLIB_ALLOWED, f"{p.relative_to(ROOT)} imports {t}")

    def test_no_dynamic_code(self):
        for p in SOURCES:
            src = p.read_text(encoding="utf-8")
            self.assertNotRegex(src, r"(?<![\w.])(eval|exec|compile)\(", p.name)
            self.assertNotIn("__import__", src, p.name)
            self.assertNotIn("pickle", src, p.name)

    def test_no_dependencies(self):
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^dependencies = \[\]$")
        self.assertNotIn("optional-dependencies", text)

    def test_no_self_update_or_install_code(self):
        bad = re.compile(r"pip install|npm install|pipx install|brew install|releases/latest|raw\.githubusercontent", re.I)
        for p in SOURCES:
            lines = p.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                if bad.search(line):
                    # only allowed inside human-readable hints shown to the user
                    context = "\n".join(lines[max(0, i - 3): i + 1]).upper()
                    self.assertIn("HINT", context, f"{p.name}:{i + 1}: {line.strip()}")

    def test_mcp_cannot_enable_cookies(self):
        from reach import mcp_server
        for t in mcp_server.TOOLS:
            self.assertNotIn("cookies", str(t["inputSchema"]).lower(), t["name"])
        o = mcp_server._opts({"url": "x", "cookies_from_browser": "chrome"})
        self.assertIsNone(o.cookies_from_browser)


if __name__ == "__main__":
    unittest.main()
