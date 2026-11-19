"""Syntax highlighting into one HTML string per source line, so the file view
can number lines and link to them. Token classes are Pygments' short names
(k, s, c, ...), coloured in app.css for both themes."""

import html

from pygments.lexers import TextLexer, get_lexer_by_name, get_lexer_for_filename
from pygments.token import STANDARD_TYPES
from pygments.util import ClassNotFound

MAX_HIGHLIGHT_BYTES = 512 * 1024
_EXTRA_NAMES = {
    "dockerfile": "docker", "makefile": "make", "gnumakefile": "make", "jenkinsfile": "groovy",
    "caddyfile": "nginx", ".env": "bash", ".bashrc": "bash", ".zshrc": "bash", ".gitignore": "text",
}


def lexer_for(filename, text=""):
    base = filename.rsplit("/", 1)[-1]
    alias = _EXTRA_NAMES.get(base.lower())
    try:
        if alias:
            return get_lexer_by_name(alias, stripnl=False, ensurenl=False)
        return get_lexer_for_filename(base, text[:4096], stripnl=False, ensurenl=False)
    except ClassNotFound:
        if text.startswith("#!"):
            first = text.split("\n", 1)[0]
            for shell, name in (("python", "python"), ("bash", "bash"), ("sh", "bash"), ("node", "javascript")):
                if shell in first:
                    return get_lexer_by_name(name, stripnl=False, ensurenl=False)
        return TextLexer(stripnl=False, ensurenl=False)


def _css_class(ttype):
    while ttype is not None:
        cls = STANDARD_TYPES.get(ttype)
        if cls is not None:
            return cls
        ttype = ttype.parent
    return ""


def highlight_lines(text, filename=None, lexer=None):
    """(language name, [html per line]). Plain escaped lines for big files."""
    lines = text.split("\n")
    if text.endswith("\n"):
        lines = lines[:-1]
    if lexer is None:
        lexer = lexer_for(filename or "", text)
    if len(text) > MAX_HIGHLIGHT_BYTES or isinstance(lexer, TextLexer):
        return ("Text" if isinstance(lexer, TextLexer) else lexer.name), [html.escape(l) for l in lines]
    out, current = [], []
    for ttype, value in lexer.get_tokens(text):
        cls = _css_class(ttype)
        pieces = value.split("\n")
        for i, piece in enumerate(pieces):
            if i > 0:
                out.append("".join(current))
                current = []
            if piece:
                escaped = html.escape(piece)
                current.append(f'<span class="{cls}">{escaped}</span>' if cls else escaped)
    if current:
        out.append("".join(current))
    return lexer.name, out[: len(lines)] + [""] * max(0, len(lines) - len(out))


def highlight_block(code, language):
    """HTML for a fenced code block in Markdown."""
    try:
        lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False) if language else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()
    _name, lines = highlight_lines(code, lexer=lexer)
    return "\n".join(lines)
