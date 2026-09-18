/** Цветная тип-иконка акта — язык FileTypeIcon из «Файлов»: кодекс — синяя
 * плашка с текстовыми строками, ФЗ — графитовая «ФЗ», судебная практика —
 * бежевая «ВС». Цвета — токены --doc-ico-codex / --doc-ico-law / --doc-ico-court. */
export function ActTypeIcon({ kind }: { kind: string }) {
  if (kind === "codex") {
    return (
      <svg className="src-aico" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
        <rect width="18" height="18" rx="5" fill="var(--doc-ico-codex)" />
        <path
          d="M5 6.2h8M5 9h8M5 11.8h5.2"
          stroke="var(--on-dark)"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  const court = kind === "court";
  return (
    <svg className="src-aico" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <rect
        width="18"
        height="18"
        rx="5"
        fill={court ? "var(--doc-ico-court)" : "var(--doc-ico-law)"}
      />
      <text x="9" y="11.8" textAnchor="middle" fontSize="6" fontWeight="700" fill="var(--on-dark)">
        {court ? "ВС" : "ФЗ"}
      </text>
    </svg>
  );
}
