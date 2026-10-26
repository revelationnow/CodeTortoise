import { describe, expect, it } from "vitest";
import { type ComponentProps, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { aiTitle } from "../lib/aiMarks";
import AiText, { AiName } from "./AiText";

const text = (props: Partial<ComponentProps<typeof AiText>> = {}) =>
  renderToStaticMarkup(createElement(AiText, { ...props, children: "The words." }));
const name = (props: Partial<ComponentProps<typeof AiName>> = {}) =>
  renderToStaticMarkup(createElement(AiName, { ...props, children: "The name" }));
/** An attribute of the outermost element; null when it has none. */
const attr = (html: string, key: string) => html.match(/^<[^>]*>/)![0].match(new RegExp(` ${key}="([^"]*)"`))?.[1] ?? null;

describe("AiText: AI-written text", () => {
  it("marks its words with the edge's class, the hover and the hidden 'Written by AI.' ahead of them", () => {
    expect(text()).toBe('<p class="ai-text" title="Written by AI"><span class="vh">Written by AI. </span>The words.</p>');
  });
  it("keeps the caller's class beside the mark", () => {
    expect(attr(text({ className: "ws-lead" }), "class")).toBe("ai-text ws-lead");
  });
  it("names the model in the hover when the caller knows it", () => {
    expect(attr(text({ by: "fake-strong" }), "title")).toBe(aiTitle("fake-strong"));
    expect(attr(text({ by: null }), "title")).toBe(aiTitle());
  });
  it("keeps the hover when a caller passes title={undefined}", () => {
    expect(attr(text({ title: undefined }), "title")).toBe(aiTitle());
    expect(attr(text({ title: undefined, by: "fake-strong" }), "title")).toBe(aiTitle("fake-strong"));
  });
  it("lets a caller's title replace the hover", () => {
    expect(attr(text({ title: "Written by AI\nthe whole intro" }), "title")).toBe("Written by AI\nthe whole intro");
    expect(attr(text({ title: "Written by AI\nthe whole intro", by: "fake-strong" }), "title")).toBe("Written by AI\nthe whole intro");
  });
  it("renders as the element it replaces", () => {
    for (const tag of ["p", "li", "div", "span"] as const) expect(text({ as: tag })).toMatch(new RegExp(`^<${tag} class="ai-text".*</${tag}>$`));
    expect(text({ as: "li" })).toMatch(/^<li /);
  });
  it("with ai={false} renders the plain element: no class, no hidden text, no hover of its own", () => {
    expect(text({ ai: false })).toBe("<p>The words.</p>");
    expect(text({ ai: false, as: "li", className: "ws-lead", by: "fake-strong" })).toBe('<li class="ws-lead">The words.</li>');
  });
  it("with ai={false} still passes a caller's own title through", () => {
    expect(text({ ai: false, title: "its own" })).toBe('<p title="its own">The words.</p>');
  });
});

describe("AiName: an AI-written name shown as a heading", () => {
  it("has the hover and the hidden 'Written by AI: ' ahead of the name, and no edge", () => {
    const html = name();
    expect(html).toBe('<span class="ai-name" title="Written by AI"><span class="vh">Written by AI: </span>The name</span>');
    expect(html).not.toContain("ai-text");
  });
  it("names the model in the hover when the caller knows it", () => {
    expect(attr(name({ by: "fake-strong" }), "title")).toBe(aiTitle("fake-strong"));
  });
  it("lets a caller's title replace the hover, where the name may be cut short", () => {
    expect(attr(name({ title: "Written by AI\nThe whole of a long name" }), "title")).toBe("Written by AI\nThe whole of a long name");
  });
  it("with ai={false} is the bare name", () => {
    expect(name({ ai: false })).toBe("The name");
  });
});
