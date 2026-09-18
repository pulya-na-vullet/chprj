import type { Element, Root, Text } from "hast";
import { visit } from "unist-util-visit";
import { findCitations } from "./citations";

// Walks hast text nodes and wraps citation spans ("ст. 1477 ГК РФ") in a
// <cite data-act data-numbers> element, mapped to <CitationChip> by renderMarkdown.
export function rehypeCitations(actNames: string[]) {
  return (tree: Root) => {
    visit(tree, "text", (node: Text, index, parent) => {
      if (index === null || !parent || (parent as Element).tagName === "cite") return;
      const matches = findCitations(node.value, actNames);
      if (matches.length === 0) return;

      const children: (Text | Element)[] = [];
      let cursor = 0;
      for (const m of matches) {
        if (m.index > cursor) children.push({ type: "text", value: node.value.slice(cursor, m.index) });
        children.push({
          type: "element",
          tagName: "cite",
          properties: { dataAct: m.act, dataNumbers: m.numbers.join(",") },
          children: [{ type: "text", value: m.raw }],
        });
        cursor = m.index + m.length;
      }
      if (cursor < node.value.length) children.push({ type: "text", value: node.value.slice(cursor) });
      // index is guaranteed non-null at this point (checked above)
      const idx = index as number;
      parent.children.splice(idx, 1, ...children);
      return idx + children.length; // skip past inserted nodes
    });
  };
}
