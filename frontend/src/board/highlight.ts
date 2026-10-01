/** Minimal C/C++ token highlighter (from the prototype). Returns tokens, never HTML. */
export interface Token { cls: string | null; text: string }

const TYPES = /^(int|unsigned|signed|char|void|bool|short|long|float|double|auto|size_t|ssize_t|[a-z0-9_]+_t)$/;
const RE = new RegExp([
  /(\/\*.*?\*\/|\/\/.*$)/.source,                                        // 1 comment
  /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/.source,                        // 2 string / char
  /(^\s*#\s*\w+)/.source,                                                // 3 preprocessor
  /\b(int|unsigned|signed|char|void|bool|short|long|float|double|auto|size_t|ssize_t|[a-z0-9_]+_t|const|struct|union|enum|class|namespace|template|typename|typedef|return|if|else|for|while|do|switch|case|default|break|continue|goto|static|extern|inline|volatile|virtual|override|public|private|protected|sizeof|new|delete|this|nullptr|true|false|NULL|constexpr|using|operator|static_cast|reinterpret_cast|const_cast|dynamic_cast)\b/.source, // 4 keyword
  /\b([A-Z_][A-Z0-9_]{2,})\b/.source,                                    // 5 macro-like
  /\b(0x[0-9a-fA-F]+|\d+(?:\.\d+)?[uUlLfF]*)\b/.source,                  // 6 number
  /\b([A-Za-z_]\w*)(?=\s*\()/.source,                                    // 7 call
].join("|"), "g");

export function tokens(src: string): Token[] {
  const out: Token[] = [];
  let last = 0;
  RE.lastIndex = 0;
  for (let m = RE.exec(src); m; m = RE.exec(src)) {
    if (m[0] === "") { RE.lastIndex++; continue; }
    if (m.index > last) out.push({ cls: null, text: src.slice(last, m.index) });
    const t = m[0];
    const cls = m[1] ? "cm" : m[2] ? "str" : m[3] ? "pp" : m[4] ? (TYPES.test(t) ? "ty" : "kw") : m[5] ? "mc" : m[6] ? "num" : "fn";
    out.push({ cls, text: t });
    last = m.index + t.length;
  }
  if (last < src.length) out.push({ cls: null, text: src.slice(last) });
  return out;
}
