import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import Markdown from "../components/Markdown";
import { descriptionParts, plainTitle } from "./markdown";

describe("plainTitle", () => {
  it("drops a CL title's Markdown so the rail and the heading read as text", () => {
    expect(plainTitle("# Fix **uart** `tx` path")).toBe("Fix uart tx path");
    expect(plainTitle("## [JOB-12](https://jobs/12): _reftable_ ~~old~~ reader")).toBe("JOB-12: reftable old reader");
    expect(plainTitle("- [ ] wip: retry")).toBe("wip: retry");
    expect(plainTitle("> quoted title")).toBe("quoted title");
  });
  it("leaves plain text, snake_case and arithmetic alone", () => {
    expect(plainTitle("uart_send: return -2 on a full FIFO")).toBe("uart_send: return -2 on a full FIFO");
    expect(plainTitle("a * b * c")).toBe("a * b * c");
    expect(plainTitle("")).toBe("");
  });
});

describe("descriptionParts", () => {
  it("splits a CL description into its title and a body whose shared indent is gone, so its Markdown renders", () => {
    const desc = "\n[JOB-7] Add frame pool.\r\n\r\n    ## Summary\r\n    - **pool**: reuse frames\r\n      - nested\r\n\n    ```c\n    pool_get();\n    ```\n";
    const { title, body } = descriptionParts(desc);
    expect(title).toBe("[JOB-7] Add frame pool.");
    expect(body).toBe("## Summary\n- **pool**: reuse frames\n  - nested\n\n```c\npool_get();\n```");
    const html = renderToStaticMarkup(createElement(Markdown, { text: body }));
    expect(html).toContain("<h2>Summary</h2>");
    expect(html).toContain("<strong>pool</strong>");
    expect(html).toContain('<code class="language-c">pool_get();');
  });
  it("counts a tab as one indent step and leaves an unindented body as written", () => {
    expect(descriptionParts("Fix\n\t- a\n\t\t- b").body).toBe("- a\n\t- b");
    expect(descriptionParts("Fix\n\n- a\n    code").body).toBe("- a\n    code");
    expect(descriptionParts("")).toEqual({ title: "", body: "" });
  });
});

const html = (text: string) => renderToStaticMarkup(createElement(Markdown, { text }));

describe("Markdown renders a Perforce description as people write it (owner, 2026-10-10)", () => {
  it("makes indented bullets a list and keeps the next line its own paragraph", () => {
    const out = html("Changes:\n    * reset FIFO on overrun\n    * count errors\nTested on board rev B");
    expect(out).toContain("<li>reset FIFO on overrun</li>");
    expect(out).toContain("<li>count errors</li>");
    expect(out).toContain("<p>Tested on board rev B</p>");
    expect(out).not.toContain("* reset");
  });
  it("keeps the nesting of tab-indented bullets", () => {
    const out = html("Steps:\n\t- one\n\t\t- sub\n\t- two");
    expect(out.replace(/\n/g, "")).toContain("<li>one<ul><li>sub</li></ul></li><li>two</li>");
  });
  it("keeps every line break", () => {
    expect(html("line one\nline two")).toContain("line one<br/>");
  });
  it("reads indented text as text, and only fenced code as code", () => {
    expect(html("Notes:\n\n    this was indented")).toContain("<p>this was indented</p>");
    expect(html("```\n  x = 1;\n```")).toContain("<pre><code>  x = 1;");
  });
  it("renders HTML spans with their colours and Markdown inside a div", () => {
    expect(html('Fixed <span style="color:red">critical</span> bug')).toContain('<span style="color:red">critical</span>');
    expect(html('<font color="red">r</font>')).toContain('<font color="red">r</font>');
    const div = html("<div>\nInside **bold** text\n</div>");
    expect(div).toContain("<div>");
    expect(div).toContain("<strong>bold</strong>");
  });
  it("keeps only colour and font styling, and nothing that runs, loads or covers the page", () => {
    expect(html('<span style="position:fixed;color:blue;background:url(http://x/y.png)">t</span>'))
      .toContain('<span style="color:blue">t</span>');
    const out = html('<script>alert(1)</script><a href="javascript:alert(1)" onclick="x()">x</a> '
      + '<img src="http://x/t.png" alt="logo"> <iframe src="http://x"></iframe><style>body{display:none}</style>');
    for (const bad of ["<script", "javascript:", "onclick", "<img", "<iframe", "<style", "display:none"]) expect(out).not.toContain(bad);
    expect(out).toContain("logo");
    expect(html("[site](https://example.com)")).toContain('target="_blank"');
  });
});

describe("plainTitle with HTML", () => {
  it("drops tags and decodes entities", () => {
    expect(plainTitle('<span style="color:red">Fix</span> uart &amp; spi &lt;3')).toBe("Fix uart & spi <3");
  });
});
