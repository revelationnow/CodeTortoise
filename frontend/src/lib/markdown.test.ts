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
