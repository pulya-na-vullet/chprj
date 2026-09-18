import { useMemo } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "../api/types";
import { CitationChip } from "../components/CitationChip";
import { CitationsProvider } from "../components/CitationsContext";
import { rehypeCitations } from "./rehypeCitations";

const REMARK_PLUGINS = [remarkGfm];

const COMPONENTS: Components = {
  // hast "cite" → our chip; cast because `cite` isn't a default element prop type.
  cite: (props) =>
    CitationChip({
      dataAct: (props as { "data-act"?: string })["data-act"],
      dataNumbers: (props as { "data-numbers"?: string })["data-numbers"],
      children: props.children,
    }),
};

export function RenderMarkdown({
  content,
  citations,
  actNames,
}: {
  content: string;
  citations: Citation[];
  actNames: string[];
}) {
  // Stable plugin/components references: react-markdown re-parses on every
  // render, so anything that re-renders this component with unchanged props
  // (or a future react-markdown memo) must not see fresh arrays each time.
  const rehypePlugins = useMemo(() => [() => rehypeCitations(actNames)], [actNames]);
  return (
    <CitationsProvider value={citations}>
      <Markdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={rehypePlugins} components={COMPONENTS}>
        {content}
      </Markdown>
    </CitationsProvider>
  );
}
