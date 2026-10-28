import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ContractRow } from "../reading/types";
import { Sig } from "./StoryTabs";

const row = (over: Partial<ContractRow>): ContractRow =>
  ({ kind: "declaration", text: "", node: null, before: "", after: "", mark: [], added: [], removed: [], nodes: [], ...over });
const html = (r: ContractRow) => renderToStaticMarkup(createElement(Sig, { row: r }));

describe("Sig: a contract row's code lines", () => {
  it("draws a changed pair, the part of the new side that differs marked", () => {
    expect(html(row({ before: "struct Widget { int a; int b; }", after: "struct Widget { int a; int c; }", mark: [27, 28] }))).toBe(
      '<div class="st-sig mono"><div class="del">struct Widget { int a; int b; }</div>' +
      '<div class="add">struct Widget { int a; int <mark>c</mark>; }</div></div>');
  });

  it("draws the one side an added declaration has, as the new side of a pair is drawn", () => {
    expect(html(row({ after: "#define LIMIT 8" }))).toBe('<div class="st-sig mono"><div class="add">#define LIMIT 8</div></div>');
  });

  it("draws the one side a removed declaration has, as the old side of a pair is drawn", () => {
    expect(html(row({ before: "int alpha(void);" }))).toBe('<div class="st-sig mono"><div class="del">int alpha(void);</div></div>');
  });

  it("draws nothing for a declaration whose texts the back end left out, nor for another kind of row with one side", () => {
    expect(html(row({}))).toBe("");
    expect(html(row({ kind: "signature", after: "void fresh(void)" }))).toBe("");
  });
});
