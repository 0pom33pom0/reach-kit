# reach-kit — Design Spec

วันที่: 2026-10-09 · สถานะ: อนุมัติแล้ว, implement ใน v1.0.0 (2026-10-22)

## 1. เป้าหมาย

เครื่องมือให้ AI agent (เน้น Claude Code) **อ่านและค้นข้อมูลจากอินเทอร์เน็ต รวมถึงคอมเมนต์** ได้หลายแพลตฟอร์ม
ออกแบบมาแทน agent-reach โดยเน้นว่า **ตรวจสอบได้ ไม่มี dependency ภายนอก ไม่อัปเดตตัวเอง**
จะเผยแพร่เป็น open source ให้คนอื่นใช้ (README ไทย + อังกฤษ)

### เกณฑ์ความสำเร็จ
- อ่านเนื้อหา + คอมเมนต์ได้ตามตารางข้อ 4 โดยไม่ต้องล็อกอิน (ยกเว้นที่ระบุ)
- คนทั่วไปอ่านโค้ดทั้งหมดและเข้าใจว่าทำอะไรได้ภายใน ~30 นาที
- ผลลัพธ์รูปแบบเดียวกันทุกแพลตฟอร์ม, error บอกเหตุผลและทางแก้เสมอ
- `reach doctor` ไม่โกหก (ทดสอบจริง ไม่ใช่แค่เช็คว่ามีโปรแกรม)

### นอกขอบเขต (YAGNI)
- แพลตฟอร์มจีน (Xiaohongshu, Bilibili, Weibo ฯลฯ)
- การโพสต์/เขียนข้อมูลกลับไปยังแพลตฟอร์ม
- การถอดเสียง (transcribe) ด้วย AI — ใช้ซับที่มีอยู่เท่านั้น
- การจัดเก็บ/อ่านคุกกี้เอง — ให้ yt-dlp จัดการเมื่อผู้ใช้สั่ง
- ระบบอัปเดตอัตโนมัติ / แจ้งเตือนเวอร์ชันใหม่

## 2. หลักการความปลอดภัย (ห้ามละเมิด — มีเทสต์บังคับ)

1. `pyproject.toml` → `dependencies = []` ใช้ Python standard library เท่านั้น (Python ≥ 3.9)
2. โปรแกรมภายนอกที่เรียกได้: `yt-dlp`, `gh` เท่านั้น ผ่าน `subprocess.run([...])` แบบ list, ห้าม `shell=True`, มี timeout ทุกครั้ง
3. ไม่มีโค้ดอัปเดตตัวเอง, ไม่มี telemetry, ไม่เรียก server ของโปรเจกต์, ไม่ดาวน์โหลดคำสั่ง/สคริปต์จากเว็บมารัน
4. SSRF guard: อนุญาตเฉพาะ `http`/`https`; ปฏิเสธ `localhost`, loopback, private/link-local/reserved IP (เช็คหลัง DNS resolve และหลัง redirect ทุกครั้ง)
5. Prompt-injection: ผลลัพธ์ markdown ครอบเนื้อหาจากเว็บด้วยเครื่องหมาย `<<<UNTRUSTED CONTENT ... >>>`; SKILL.md สั่งชัดว่าเนื้อหาในนั้นเป็นข้อมูล ห้ามทำตาม
6. คุกกี้: ไม่เก็บ ไม่อ่านเอง ส่งต่อให้ `yt-dlp --cookies-from-browser` เฉพาะเมื่อผู้ใช้ใส่ flag ในคำสั่งนั้น ไม่มีการจำค่า
7. ความลับที่อนุญาต (ทางเลือก): `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`, `JINA_API_KEY` อ่านจาก env เท่านั้น ห้ามพิมพ์ออก log/output
8. ไฟล์ทั้งหมดอยู่ใต้ `~/.cache/reach-kit/` (สิทธิ์ 0700), cache หมดอายุ 24 ชม., จำกัด 200MB, ไฟล์ temp ลบใน `finally`

## 3. สถาปัตยกรรม

```
reach-kit/
├── reach/
│   ├── __init__.py         __version__
│   ├── model.py            dataclass Item / Comment / Result + to_json / to_markdown
│   ├── errors.py           ReachError(code, message, tried[], hint)
│   ├── net.py              http_get (urllib) + SSRF guard + UA + timeout + size limit
│   ├── cache.py            file cache (sha256 key, TTL, size cap)
│   ├── proc.py             run_tool("yt-dlp"|"gh", args) — allowlist + timeout
│   ├── router.py           url → channel
│   ├── channels/
│   │   ├── web.py          Jina Reader → direct fetch + HTML→text
│   │   ├── search.py       DuckDuckGo HTML → (ถ้ามี JINA_API_KEY) s.jina.ai
│   │   ├── youtube.py      yt-dlp: metadata, subtitles, comments
│   │   ├── social.py       tiktok / x / facebook / instagram (yt-dlp → Jina)
│   │   ├── reddit.py       public JSON → OAuth app-only (ถ้ามี env) → error
│   │   ├── pantip.py       หน้ากระทู้ + /forum/topic/render_comments
│   │   ├── github.py       gh api (repo, issue, PR + comments)
│   │   ├── hn.py           HN Algolia API (story + comment tree)
│   │   ├── arxiv.py        export.arxiv.org API (Atom)
│   │   └── rss.py          RSS/Atom ด้วย xml.etree
│   ├── doctor.py           live probe ทุกช่องทาง (timeout 10s/ช่อง, รันขนาน)
│   ├── cli.py              argparse entry point `reach`
│   ├── mcp_server.py       MCP stdio JSON-RPC (เขียนเอง) เรียก core เดียวกับ CLI
│   └── skill/              SKILL.md + references/*.md (ติดตั้งผ่าน `reach install-skill`)
├── tests/                  unittest + fixtures/ (JSON/HTML ที่บันทึกไว้)
├── .github/workflows/ci.yml   macOS / Linux / Windows × Python 3.9, 3.12
├── pyproject.toml          hatchling, dependencies = []
├── README.md / README_th.md / SECURITY.md / CHANGELOG.md / LICENSE (MIT)
```

แต่ละ channel มีอินเทอร์เฟซเดียวกัน:

```python
def read(url: str, opts: Options) -> Result      # เนื้อหาหลัก (+ comments ถ้า opts.comments)
def comments(url: str, opts: Options) -> Result   # เฉพาะคอมเมนต์ (ถ้ารองรับ)
def probe() -> ProbeResult                         # ใช้โดย doctor
```

CLI, MCP, และ SKILL ทั้งสามเรียกผ่าน `router` → channel เดียวกัน ไม่มี logic ซ้ำ

## 4. ความสามารถรายแพลตฟอร์ม

| แพลตฟอร์ม | เนื้อหา | คอมเมนต์ | วิธี (ตามลำดับ fallback) |
|---|---|---|---|
| เว็บทั่วไป | ✅ | — | Jina Reader → direct fetch + HTML→text |
| ค้นหาเว็บ | ✅ | — | DuckDuckGo HTML → s.jina.ai (ต้องมี `JINA_API_KEY`) |
| YouTube | ✅ meta + ซับ | ✅ | yt-dlp |
| TikTok | ✅ | 🟡 ขึ้นกับ TikTok | yt-dlp → Jina |
| X | 🟡 โพสต์สาธารณะ | ❌ (🟡 ถ้าใช้คุกกี้) | yt-dlp → Jina |
| Facebook / Instagram | 🟡 โพสต์/คลิปสาธารณะ | ❌ | yt-dlp → Jina |
| Reddit | ✅* | ✅* | public JSON → OAuth app-only → error พร้อมวิธีตั้ง app |
| Pantip | ✅ | ✅ (+ reply) | page + render_comments (แบ่งหน้า) |
| GitHub | ✅ | ✅ issue/PR | `gh` |
| Hacker News | ✅ | ✅ tree | Algolia API |
| ArXiv | ✅ abstract + meta | — | export API |
| RSS/Atom | ✅ | — | xml.etree |

\* ทดสอบ 2026-10-09: Reddit บล็อก anonymous จาก IP ที่ทดสอบทุกเส้นทาง (403) จึงต้องรองรับ OAuth app-only
(ผู้ใช้สร้าง "script app" ของตัวเองที่ reddit.com/prefs/apps) — ไม่ใช้คุกกี้, ไม่ต้องล็อกอินบัญชี

### กฎเฉพาะ
- **YouTube ซับ**: เลือก manual sub ภาษาต้นฉบับก่อน → manual ภาษาที่ขอ → auto-generated; ถ้าเป็น auto หรือแปลด้วยเครื่อง ต้องเพิ่มใน `warnings`
- **คอมเมนต์**: `--limit` (ค่าเริ่มต้น 50), `--sort top|new`, `--depth` (ค่าเริ่มต้น 2) ใช้ได้ทุกแพลตฟอร์มที่รองรับ
- **คุกกี้**: `--cookies-from-browser <browser>` ใช้ได้เฉพาะช่องทางที่ผ่าน yt-dlp; แสดงคำเตือนความเสี่ยงโดนแบนทุกครั้ง; หน่วงเวลาขั้นต่ำ 2 วินาทีระหว่างคำขอ

## 5. รูปแบบผลลัพธ์

```json
{
  "platform": "pantip",
  "url": "https://pantip.com/topic/43000000",
  "title": "...", "author": "...", "published": "2026-10-01T12:00:00Z",
  "text": "...",
  "stats": {"likes": 120, "comments": 45, "views": null},
  "comments": [{"author": "...", "text": "...", "likes": 12, "published": "...", "replies": []}],
  "source": "pantip:render_comments",
  "warnings": [],
  "truncated": false
}
```

- markdown (ค่าเริ่มต้น) แปลงจาก JSON นี้ + ครอบ UNTRUSTED CONTENT
- `--max-chars` (ค่าเริ่มต้น 20,000) ตัดแบบมี `truncated: true`
- error: exit code ≠ 0, ออก stderr (หรือ JSON `{"error": {code, message, tried, hint}}` เมื่อ `--json`)

## 6. CLI

```
reach read <url> [--comments]
reach comments <url> [--limit N] [--sort top|new] [--depth N]
reach transcript <youtube-url> [--lang th,en]
reach search "<query>" [--limit N]
reach feed <rss-url> [--limit N]
reach hn [top|new|search "<q>"]       reach arxiv "<query>"
reach doctor [--json]
reach install-skill [--target ~/.claude/skills] [--force]
reach mcp                              # เริ่ม MCP server (stdio)
ตัวเลือกร่วม: --json --max-chars N --no-cache --cookies-from-browser B --timeout S
```

## 7. MCP server

- เขียนเองบน stdio JSON-RPC 2.0 (newline-delimited) รองรับ `initialize`, `tools/list`, `tools/call`, `ping`, notification `initialized`
- tools: `reach_read`, `reach_comments`, `reach_transcript`, `reach_search`, `reach_feed`, `reach_hn`, `reach_arxiv`, `reach_doctor`
- ผลลัพธ์เป็น text content (markdown) ; error ส่งเป็น `isError: true` พร้อมข้อความ
- ไม่มี tool ที่เขียนไฟล์ รันคำสั่ง หรือแก้ config

## 8. Error handling

- ทุก channel มีลำดับ fallback; ถ้าทุกทางล้มเหลว → `ReachError` บอก `tried` (แต่ละวิธี + สาเหตุ) และ `hint`
- ได้ข้อมูลบางส่วน → คืนผลพร้อม `warnings` ไม่ล้มทั้งหมด
- ไม่ retry อัตโนมัติ ยกเว้น `--retry N`
- รหัส error มาตรฐาน: `blocked`, `not_found`, `login_required`, `tool_missing`, `timeout`, `invalid_url`, `unsafe_url`, `parse_error`

## 9. Doctor

- probe จริงด้วย URL/คำค้นตัวอย่างที่คงที่ (ระบุในโค้ด) ทุกช่องทาง ขนานกัน timeout 10s/ช่อง, รวมไม่เกิน 30s
- สถานะ: ✅ ok / 🟡 partial (เช่น อ่านโพสต์ได้แต่คอมเมนต์ไม่ได้) / ❌ fail + เหตุผล + วิธีแก้
- แสดงเวอร์ชัน yt-dlp / gh ที่พบ (ไม่ติดตั้งให้)

## 10. Skill

- `SKILL.md` สั้น (description ≤ 1024 ตัวอักษร): เมื่อไรควรใช้, ตารางคำสั่ง, กฎ UNTRUSTED CONTENT, ห้ามติดตั้ง/อัปเดตอะไรเอง
- `references/` แยกตามหมวด (web, video, social, community, dev)
- `reach install-skill`: คัดลอกทั้งโฟลเดอร์; ถ้าปลายทางมีอยู่และต่างกัน → ไม่เขียนทับ เว้นแต่ `--force`

## 11. การทดสอบ

- `python -m unittest` — ไม่ต้องติดตั้งอะไร
- **unit**: parser ทุก channel กับ fixtures ที่บันทึกไว้ (ไม่ต่อเน็ต; `net.http_get` และ `proc.run_tool` ถูก mock)
- **security**: SSRF (localhost, 127.0.0.1, 10.x, 169.254.x, IPv6 ::1, redirect ไป private), ไม่มี `shell=True` ใน source, `dependencies == []`, ไม่มี import ที่อยู่นอก stdlib, ไม่มี URL ไปยัง endpoint อัปเดต
- **consistency**: ชื่อคำสั่งใน SKILL.md == CLI subcommands == MCP tools; description ≤ 1024
- **mcp**: ส่ง JSON-RPC จริงผ่าน subprocess stdin/stdout
- **packaging**: build wheel แล้วเช็คว่ามี `skill/` ครบ
- **live** (`REACH_LIVE=1`): ยิงจริงทุกช่องทาง รันเองเป็นครั้งคราว ไม่อยู่ใน CI
- CI: GitHub Actions, macOS/Ubuntu/Windows × Python 3.9/3.12

## 12. การติดตั้งและเผยแพร่

```bash
brew install yt-dlp     # หรือ pipx install yt-dlp ; gh เป็นทางเลือก
pipx install "git+https://github.com/<owner>/reach-kit@v1.0.0"
reach install-skill
claude mcp add reach -- reach mcp     # ถ้าต้องการ MCP
```

- ปล่อยเวอร์ชันผ่าน git tag; README อธิบายวิธีตรวจ diff ก่อนอัปเดต
- SECURITY.md: นโยบายข้อ 2 + วิธีรายงานช่องโหว่ (GitHub private advisory)

## 13. ความเสี่ยงที่ทราบ

- แพลตฟอร์มเปลี่ยน API/บล็อก (Reddit, TikTok, X) — บรรเทาด้วย fallback + doctor ที่บอกตรง
- DuckDuckGo HTML อาจ rate-limit — มี cache + ทางเลือก JINA_API_KEY
- Pantip endpoint ไม่ใช่ API ทางการ — อาจเปลี่ยนได้; มี fixture test + live test
- yt-dlp เป็น dependency ภายนอกเพียงตัวเดียวที่สำคัญ — ผู้ใช้ติดตั้งเอง, doctor แสดงเวอร์ชัน

## 14. สิ่งที่เปลี่ยนจาก spec ระหว่าง implement (ทดสอบจริง 2026-10-22)

- **ค้นหาเว็บ**: `s.jina.ai` ต้องใช้ key และ DuckDuckGo/Mojeek ขึ้น bot check หลังไม่กี่ครั้ง → ลำดับเป็น Brave API (`BRAVE_API_KEY`) → Jina (`JINA_API_KEY`) → DuckDuckGo; SKILL แนะนำให้ใช้ web search ในตัวของ agent ก่อน
- **X**: ใช้ public embed endpoint (`cdn.syndication.twimg.com`) อ่านโพสต์เดี่ยวได้โดยไม่ล็อกอิน (yt-dlp ใช้ได้เฉพาะโพสต์ที่มีวิดีโอ)
- **TikTok**: เพิ่ม oEmbed เป็น fallback; คอมเมนต์ถูกบล็อกจากเครือข่ายที่ทดสอบ → แสดง warning
- **ไม่รองรับ `--retry`**: ตัดออกตาม YAGNI; doctor + error hint เพียงพอ
- **MCP ไม่เปิดตัวเลือกคุกกี้** เพื่อไม่ให้ model/หน้าเว็บสั่งใช้การล็อกอินของผู้ใช้เอง
- **cache TTL** แยกตามประเภท: read 1 ชม., transcript 24 ชม., search/feed/hn 15 นาที
