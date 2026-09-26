import type { ReactNode } from "react";

// A small, dependency-free Python highlighter. Good enough for agent-written scripts.
const KEYWORDS = new Set([
  "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del",
  "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
  "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
]);
const BUILTINS = new Set([
  "print", "len", "range", "sum", "min", "max", "sorted", "list", "dict", "set", "tuple", "str", "int", "float",
  "abs", "round", "enumerate", "zip", "isinstance", "open", "any", "all", "map", "filter", "type", "repr", "bool",
  "Decimal",
]);

const TOKEN_RE =
  /(#[^\n]*)|([rbfuRBFU]{0,2}"""[\s\S]*?"""|[rbfuRBFU]{0,2}'''[\s\S]*?'''|[rbfuRBFU]{0,2}"(?:\\.|[^"\\\n])*"|[rbfuRBFU]{0,2}'(?:\\.|[^'\\\n])*')|(\b\d+(?:\.\d+)?\b)|(@[A-Za-z_]\w*)|([A-Za-z_]\w*)|(\s+)|([^\sA-Za-z_\d])/g;

export function highlightPython(code: string): ReactNode[] {
  const out: ReactNode[] = [];
  let m: RegExpExecArray | null;
  let i = 0;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(code)) !== null) {
    const [tok, comment, str, num, deco, ident] = m;
    const key = i++;
    if (comment) out.push(<span key={key} className="tok-comment">{tok}</span>);
    else if (str) out.push(<span key={key} className="tok-string">{tok}</span>);
    else if (num) out.push(<span key={key} className="tok-number">{tok}</span>);
    else if (deco) out.push(<span key={key} className="tok-deco">{tok}</span>);
    else if (ident) {
      if (KEYWORDS.has(ident)) out.push(<span key={key} className="tok-keyword">{tok}</span>);
      else if (BUILTINS.has(ident)) out.push(<span key={key} className="tok-builtin">{tok}</span>);
      else {
        const rest = code.slice(TOKEN_RE.lastIndex);
        if (/^\s*\(/.test(rest)) out.push(<span key={key} className="tok-fn">{tok}</span>);
        else out.push(tok);
      }
    } else out.push(tok);
  }
  return out;
}
