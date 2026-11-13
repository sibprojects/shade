import pytest
from PySide6.QtGui import QTextCursor, QTextDocument

from shade.ui.hint_view import CODE_FG, SYNTAX, style_code_blocks


def _doc(md, qapp):
    d = QTextDocument()
    d.setMarkdown(md)
    style_code_blocks(d, 12)
    return d


def _color_of(doc, word, nth=0):
    """Foreground color of the first character of the nth occurrence of `word`."""
    text = doc.toPlainText()
    pos = -1
    for _ in range(nth + 1):
        pos = text.index(word, pos + 1)
    c = QTextCursor(doc)
    c.setPosition(pos + 1)  # charFormat() reports the char before the cursor
    return c.charFormat().foreground().color().name()


PY = """```python
def total(items):
    # sum of prices
    return sum(i.price for i in items) + 10, "done"
```"""

PHP = """```php
<?php
function greet(string $name): string {
    // say hi
    return "Hello, " . $name . 42;
}
```"""

GO = """```go
package main

func add(a int, b int) int {
    // add two numbers
    return a + b + 7 // "x"
}
var s = "text"
```"""


def test_python(qapp):
    d = _doc(PY, qapp)
    assert _color_of(d, "def") == SYNTAX["keyword"]
    assert _color_of(d, "return") == SYNTAX["keyword"]
    assert _color_of(d, "total") == SYNTAX["function"]
    assert _color_of(d, "# sum") == SYNTAX["comment"]
    assert _color_of(d, '"done"') == SYNTAX["string"]
    assert _color_of(d, "10") == SYNTAX["number"]
    assert _color_of(d, "sum(") == SYNTAX["builtin"]


def test_php_without_open_tag_too(qapp):
    d = _doc(PHP, qapp)
    assert _color_of(d, "function") == SYNTAX["keyword"]
    assert _color_of(d, "$name") == SYNTAX["variable"]
    assert _color_of(d, "// say") == SYNTAX["comment"]
    assert _color_of(d, '"Hello') == SYNTAX["string"]
    assert _color_of(d, "42") == SYNTAX["number"]
    d2 = _doc("```php\n$total = count($items);\n```", qapp)
    assert _color_of(d2, "$total") == SYNTAX["variable"]


def test_go(qapp):
    d = _doc(GO, qapp)
    assert _color_of(d, "func") == SYNTAX["keyword"]
    assert _color_of(d, "package") == SYNTAX["keyword"]
    assert _color_of(d, "add") == SYNTAX["function"]
    assert _color_of(d, "// add") == SYNTAX["comment"]
    assert _color_of(d, '"text"') == SYNTAX["string"]
    assert _color_of(d, "7") == SYNTAX["number"]


@pytest.mark.parametrize("fence", ["py", "golang", "PHP", "Python"])
def test_language_aliases(qapp, fence):
    code = {"py": "def f(): pass", "python": "def f(): pass", "golang": "func f() {}", "php": "function f() {}"}
    d = _doc(f"```{fence}\n{code[fence.lower()]}\n```", qapp)
    word = {"py": "def", "python": "def", "golang": "func", "php": "function"}[fence.lower()]
    assert _color_of(d, word) == SYNTAX["keyword"]


def test_unknown_or_missing_language_stays_plain(qapp):
    for md in ("```\ndef f(): pass\n```", "```brainfuck\n+++.\n```"):
        d = _doc(md, qapp)
        first = d.toPlainText().strip()[0]
        assert _color_of(d, first) == CODE_FG.name()


def test_text_outside_code_is_not_colored(qapp):
    d = _doc("Use def here.\n\n" + PY, qapp)
    assert _color_of(d, "Use") != SYNTAX["keyword"]
    assert _color_of(d, "def", nth=0) != SYNTAX["keyword"]  # the word in the sentence
    assert _color_of(d, "def", nth=1) == SYNTAX["keyword"]
