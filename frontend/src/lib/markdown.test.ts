import { describe, expect, it } from "vitest";
import { plainTitle } from "./markdown";

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
