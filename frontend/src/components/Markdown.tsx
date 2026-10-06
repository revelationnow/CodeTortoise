import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** User-written Markdown (a CL description), GitHub-flavoured. Raw HTML is never rendered, unsafe link schemes are
 * dropped by react-markdown, and links open in a new tab. */
export default function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml
                     components={{ a: ({ node: _node, ...p }) => <a {...p} target="_blank" rel="noreferrer noopener" /> }}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
