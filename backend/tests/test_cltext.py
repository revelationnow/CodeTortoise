"""CL descriptions as text for prompts and one-line summaries (owner feedback 2026-10-10)."""
from test_stories import _edit, _world

from codetortoise.board import build_about
from codetortoise.cltext import first_line, prompt_text

DESC = '\n<span style="color:red">Fix</span> **uart** &amp; `spi`\n\n<div>\nDetails:\n    * a\n</div>\n'


def test_a_prompt_gets_the_description_without_html_but_with_its_markdown():
    assert prompt_text(DESC) == "Fix **uart** & `spi`\n\n\nDetails:\n    * a"


def test_a_one_line_summary_is_the_first_line_as_plain_text():
    assert first_line(DESC) == "Fix uart & spi"
    assert first_line("# [JOB-12](https://jobs/12): _reftable_ ~~old~~ reader") == "JOB-12: reftable old reader"
    assert first_line("- [ ] wip: retry") == "wip: retry"
    assert first_line("uart_send: return -2 when a * b") == "uart_send: return -2 when a * b"
    assert first_line("") == ""


def test_the_template_intent_names_each_cl_by_its_first_line_not_its_raw_description():
    c = _world([_edit("send", "drv/uart.c")])
    c.cs.cls[0].description = DESC
    assert build_about(c).intent == "1 function(s) changed in 1 file(s). CL 1: Fix uart & spi."
