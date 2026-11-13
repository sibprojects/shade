"""Syntax colors for code blocks in hints (PHP, Python, Go), on a black background."""

from __future__ import annotations

from pygments import lex
from pygments.lexer import Lexer
from pygments.lexers import GoLexer, PhpLexer, PythonLexer
from pygments.token import Comment, Keyword, Name, Number, Operator, String, _TokenType

# One Dark-like colors, readable on black.
SYNTAX = {
    "keyword": "#c678dd",
    "string": "#98c379",
    "comment": "#7f848e",
    "number": "#d19a66",
    "function": "#61afef",
    "builtin": "#56b6c2",
    "type": "#e5c07b",
    "variable": "#e06c75",
}

_LEXERS = {
    # stripnl=False keeps token offsets aligned with the text.
    "python": lambda: PythonLexer(stripnl=False),
    "py": lambda: PythonLexer(stripnl=False),
    "python3": lambda: PythonLexer(stripnl=False),
    # Answers often show PHP without the opening <?php tag.
    "php": lambda: PhpLexer(startinline=True, stripnl=False),
    "go": lambda: GoLexer(stripnl=False),
    "golang": lambda: GoLexer(stripnl=False),
}

# Most specific first: a token takes the color of the first type it belongs to.
_ROLES: list[tuple[_TokenType, str]] = [
    (Comment, "comment"),
    (String, "string"),
    (Number, "number"),
    (Keyword.Type, "type"),
    (Keyword, "keyword"),
    (Operator.Word, "keyword"),
    (Name.Function, "function"),
    (Name.Decorator, "function"),
    (Name.Class, "type"),
    (Name.Builtin.Pseudo, "keyword"),
    (Name.Builtin, "builtin"),
    (Name.Variable, "variable"),
]


def lexer_for(language: str) -> Lexer | None:
    make = _LEXERS.get(language.strip().lower())
    return make() if make else None


def role_of(token: _TokenType) -> str | None:
    for kind, role in _ROLES:
        if token in kind:
            return role
    return None


def spans(code: str, lexer: Lexer) -> list[tuple[int, int, str]]:
    """(start, end, role) for each colored piece of `code`."""
    tokens = list(lex(code, lexer))
    out = []
    pos = 0
    for i, (token, text) in enumerate(tokens):
        role = role_of(token)
        if role is None and token in Name and _next_is_call(tokens, i):
            role = "function"  # Go's lexer doesn't mark functions: a name before "(" is one
        if role and text.strip():
            out.append((pos, pos + len(text), role))
        pos += len(text)
    return out


def _next_is_call(tokens, i: int) -> bool:
    for _, text in tokens[i + 1:]:
        if text.strip():
            return text.startswith("(")
    return False
