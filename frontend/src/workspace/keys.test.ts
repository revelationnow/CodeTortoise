import { describe, expect, it } from "vitest";
import { lowerKey } from "./keys";

describe("lowerKey", () => {
  const press = (key?: string) => ({ key }) as KeyboardEvent;

  it("is the key in lower case, so Caps Lock and Shift, which send J, K and F as capitals, press the same shortcuts", () => {
    expect(["j", "J", "k", "K", "f", "F"].map((k) => lowerKey(press(k)))).toEqual(["j", "j", "k", "k", "f", "f"]);
  });

  it("is any other key's name in lower case: none of them is J, K or F", () => {
    expect(["ArrowDown", "Enter", " ", "1", "Escape"].map((k) => lowerKey(press(k)))).toEqual(["arrowdown", "enter", " ", "1", "escape"]);
  });

  it("is empty for a press that carries no key, as Chrome's autofill sends", () => {
    expect(lowerKey(press())).toBe("");
  });
});
