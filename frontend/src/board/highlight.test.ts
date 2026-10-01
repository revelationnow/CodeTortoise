import { describe, expect, it } from "vitest";
import { tokens } from "./highlight";

describe("highlight", () => {
  it("classifies C tokens and keeps the text intact", () => {
    const src = '    if (len > 64) { *err += 1; return uart_send(u, "x\\n", REG_CTRL); } // overflow';
    const t = tokens(src);
    expect(t.map((x) => x.text).join("")).toBe(src);
    const cls = (text: string) => t.find((x) => x.text === text)?.cls;
    expect(cls("if")).toBe("kw");
    expect(cls("64")).toBe("num");
    expect(cls("uart_send")).toBe("fn");
    expect(cls('"x\\n"')).toBe("str");
    expect(cls("REG_CTRL")).toBe("mc");
    expect(cls("// overflow")).toBe("cm");
  });

  it("marks types and preprocessor lines", () => {
    expect(tokens("unsigned int x;").filter((x) => x.cls === "ty").map((x) => x.text)).toEqual(["unsigned", "int"]);
    expect(tokens("uint32_t v;")[0]).toEqual({ cls: "ty", text: "uint32_t" });
    expect(tokens('#include "a.h"')[0]).toEqual({ cls: "pp", text: "#include" });
  });
});
