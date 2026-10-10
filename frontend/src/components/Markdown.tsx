import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { prepareMarkdown } from "../lib/markdown";

/** HTML a description may use: GitHub's safe set plus span, div, font, u and mark; `style` on any tag (filtered below);
 * links to http, https and mailto only. Scripts and style sheets go with their content. */
const SCHEMA = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), "span", "div", "font", "u", "mark", "center"],
  attributes: { ...defaultSchema.attributes, "*": [...(defaultSchema.attributes?.["*"] ?? []), "style"], font: ["color"] },
  protocols: { ...defaultSchema.protocols, href: ["http", "https", "mailto"] },
  strip: [...(defaultSchema.strip ?? []), "style"],
};
const STYLE_OK = new Set(["color", "background-color", "font-weight", "font-style", "text-decoration"]);

type El = { type: string; properties?: Record<string, unknown>; children?: El[] };
/** Keeps only colour and font declarations of a `style`, and none that loads anything: a description may colour its
 * text but not move, cover or fetch. */
function keepSafeStyle() {
  const walk = (n: El) => {
    const style = n.properties?.style;
    if (typeof style === "string") {
      const kept = style.split(";").map((d) => d.split(":")).filter(([p, ...v]) => {
        const value = v.join(":").trim();
        return p && STYLE_OK.has(p.trim().toLowerCase()) && /^[#\w\s,.()%-]+$/.test(value) && !/url|expression/i.test(value);
      }).map(([p, ...v]) => `${p.trim().toLowerCase()}:${v.join(":").trim()}`).join(";");
      if (kept) n.properties!.style = kept; else delete n.properties!.style;
    }
    n.children?.forEach(walk);
  };
  return (tree: El) => walk(tree);
}

/** User-written Markdown with HTML (a CL description), GitHub-flavoured, line breaks kept, prepared the way Perforce
 * authors write it (`prepareMarkdown`). HTML goes through a sanitizer and a style filter; images show their alt text
 * (no outside fetch); links open in a new tab. */
export default function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}
                     rehypePlugins={[rehypeRaw, [rehypeSanitize, SCHEMA], keepSafeStyle]}
                     components={{
                       a: ({ node: _node, ...p }) => <a {...p} target="_blank" rel="noreferrer noopener" />,
                       img: ({ alt }) => (alt ? <span className="md-alt">{alt}</span> : null),
                     }}>
        {prepareMarkdown(text)}
      </ReactMarkdown>
    </div>
  );
}
