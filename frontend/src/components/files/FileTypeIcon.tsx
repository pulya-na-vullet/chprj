/** Цветная тип-иконка файла: синяя плашка с текстовыми строками для DOCX,
 * красная с надписью PDF. Цвета — токены --doc-ico-docx / --doc-ico-pdf. */
export function FileTypeIcon({ parser }: { parser: string }) {
  if (parser === "pdf") {
    return (
      <svg className="file-ico" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
        <rect width="18" height="18" rx="5" fill="var(--doc-ico-pdf)" />
        <text
          x="9"
          y="11.8"
          textAnchor="middle"
          fontSize="6"
          fontWeight="700"
          fill="var(--on-dark)"
        >
          PDF
        </text>
      </svg>
    );
  }
  return (
    <svg className="file-ico" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <rect width="18" height="18" rx="5" fill="var(--doc-ico-docx)" />
      <path
        d="M5 6.2h8M5 9h8M5 11.8h5.2"
        stroke="var(--on-dark)"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}
