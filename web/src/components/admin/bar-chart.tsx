/** Grafico a barre minimale in SVG (server component, niente JS client). */
export function BarChart({
  data,
  height = 120,
}: {
  data: { label: string; value: number }[];
  height?: number;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const barW = 100 / data.length;

  return (
    <div className="w-full">
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="h-32 w-full overflow-visible">
        <defs>
          <linearGradient id="barg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#a78bfa" stopOpacity="0.9" />
            <stop offset="1" stopColor="#6c63ff" stopOpacity="0.25" />
          </linearGradient>
        </defs>
        {data.map((d, i) => {
          const h = (d.value / max) * (height - 8);
          return (
            <g key={i}>
              <rect
                x={i * barW + barW * 0.18}
                y={height - h}
                width={barW * 0.64}
                height={Math.max(h, 1.5)}
                rx="1.2"
                fill="url(#barg)"
              >
                <title>{`${d.label}: ${d.value}`}</title>
              </rect>
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex justify-between font-mono text-[10px] text-fg-dim">
        <span>{data[0]?.label}</span>
        <span>{data[data.length - 1]?.label}</span>
      </div>
    </div>
  );
}
