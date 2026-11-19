"""README and .md rendering: CommonMark + GitHub tables, strikethrough and
task lists, sanitized with nh3. Relative links point into the repository."""

import html
import posixpath
from urllib.parse import quote

import nh3
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

from highlight import highlight_block

TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "dd", "del", "details", "div", "dl", "dt", "em", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "i", "img", "input", "kbd", "li", "ol", "p", "picture", "pre", "q", "s",
    "samp", "source", "span", "strike", "strong", "sub", "summary", "sup", "table", "tbody", "td", "tfoot",
    "th", "thead", "tr", "tt", "u", "ul", "var", "video",
}
ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height", "align"},
    "source": {"srcset", "media", "type"},
    "video": {"src", "controls", "width", "height", "poster"},
    "code": {"class"},
    "span": {"class"},
    "pre": {"class"},
    "td": {"align", "colspan", "rowspan"},
    "th": {"align", "colspan", "rowspan"},
    "input": {"type", "checked", "disabled"},
    "ol": {"start"},
    "li": {"class"},
    "ul": {"class"},
    "div": {"align"},
    "p": {"align"},
    "h1": {"align"}, "h2": {"align"}, "h3": {"align"},
    "details": {"open"},
}
SCHEMES = {"http", "https", "mailto"}


def _md():
    md = MarkdownIt("commonmark", {"html": True, "linkify": False, "typographer": False})
    md.enable(["table", "strikethrough"])
    md.use(tasklists_plugin)

    def fence(code, lang, _attrs):
        return f'<pre class="code"><code class="hl">{highlight_block(code, (lang or "").split()[0] if lang else "")}</code></pre>'

    md.options["highlight"] = fence
    return md


_MD = _md()


def _is_relative(url):
    lowered = url.strip().lower()
    return lowered and not (lowered.startswith(("#", "//", "data:")) or ":" in lowered.split("/", 1)[0])


def _repo_url(base, kind, ref, doc_dir, url):
    target, _, fragment = url.partition("#")
    target, _, query = target.partition("?")
    if target.startswith("/"):
        joined = posixpath.normpath(target.lstrip("/"))
    else:
        joined = posixpath.normpath(posixpath.join(doc_dir, target))
    if joined.startswith(".."):
        return None
    joined = "" if joined == "." else joined
    out = f"{base}/{kind}/{quote(ref, safe='/')}/{quote(joined, safe='/')}".rstrip("/")
    return out + (f"#{fragment}" if fragment else "")


def render_markdown(text, owner=None, repo=None, ref=None, doc_path=""):
    """Safe HTML. With owner/repo/ref, relative image sources load from the raw
    URL and relative links open the file or folder in the repository."""
    raw_html = _MD.render(text)
    base = f"/{quote(owner)}/{quote(repo)}" if owner and repo else None
    doc_dir = posixpath.dirname(doc_path or "")

    def rewrite(tag, attr, value):
        if base and ref and attr in ("src", "href", "poster") and _is_relative(value):
            kind = "raw" if attr in ("src", "poster") else "blob"
            new = _repo_url(base, kind, ref, doc_dir, value)
            return new
        return value

    return nh3.clean(raw_html, tags=TAGS, attributes=ATTRIBUTES, attribute_filter=rewrite, url_schemes=SCHEMES,
                     link_rel="noopener noreferrer nofollow")


def escape(text):
    return html.escape(text)
