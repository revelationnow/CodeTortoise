import { describe, expect, it } from "vitest";
import { insertMention, mentionOptions, mentionQuery } from "./mention";

describe("mentionQuery", () => {
  it("finds the @word being typed at the caret", () => {
    expect(mentionQuery("hi @tor", 7)).toEqual({ start: 3, query: "tor" });
    expect(mentionQuery("@", 1)).toEqual({ start: 0, query: "" });
    expect(mentionQuery("line one\n@b", 11)).toEqual({ start: 9, query: "b" });
  });
  it("ignores an @ inside a word, after a space, or before the caret's word", () => {
    expect(mentionQuery("me@tortoise", 11)).toBeNull();
    expect(mentionQuery("@bob ", 5)).toBeNull();
    expect(mentionQuery("@bob hi", 7)).toBeNull();
  });
});

describe("mentionOptions", () => {
  const ai = { ok: true, detail: "ask the AI" };
  it("puts tortoise first, then people, narrowed by the query", () => {
    expect(mentionOptions("", ["owner", "bob"], ai).map((o) => o.name)).toEqual(["tortoise", "owner", "bob"]);
    expect(mentionOptions("b", ["owner", "bob"], ai).map((o) => o.name)).toEqual(["bob"]);
    expect(mentionOptions("TO", ["owner", "bob"], ai).map((o) => o.name)).toEqual(["tortoise"]);
  });
  it("shows tortoise disabled with the reason when it can't run, and never lists it as a person", () => {
    const [t, ...rest] = mentionOptions("", ["tortoise", "bob"], { ok: false, detail: "no AI is configured" });
    expect(t).toMatchObject({ name: "tortoise", disabled: true, detail: "no AI is configured" });
    expect(rest.map((o) => o.name)).toEqual(["bob"]);
  });
});

describe("insertMention", () => {
  it("replaces the typed @word with the name and a space, caret after it", () => {
    expect(insertMention("hi @tor", 3, 7, "tortoise")).toEqual({ text: "hi @tortoise ", caret: 13 });
    expect(insertMention("@b and more", 0, 2, "bob")).toEqual({ text: "@bob and more", caret: 5 });   // no double space
  });
});
