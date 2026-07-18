import type { SocHistoryBucketSchema } from "@golfcart/client";
import { useState } from "react";

const CHART_HEIGHT = 112;
const Y_TICKS = [0, 50, 100];

interface SocHistoryChartProps {
  buckets: SocHistoryBucketSchema[];
}

interface StepSegment {
  hasData: boolean;
  d: string;
}

function yFor(socPercent: number | null | undefined) {
  return 100 - Math.min(100, Math.max(0, socPercent ?? 0));
}

function buildStepSegments(buckets: SocHistoryBucketSchema[]): StepSegment[] {
  const n = buckets.length;
  const segments: StepSegment[] = [];
  let points: [number, number][] = [];
  let hasData = buckets[0]?.has_data ?? true;

  buckets.forEach((bucket, i) => {
    const xStart = (i / n) * 100;
    const xEnd = ((i + 1) / n) * 100;
    const y = yFor(bucket.soc_percent);

    if (bucket.has_data !== hasData) {
      const prevY = yFor(buckets[i - 1]?.soc_percent);
      points.push([xStart, prevY]);
      segments.push({ hasData, d: toPath(points) });
      points = [];
      hasData = bucket.has_data;
    }
    points.push([xStart, y], [xEnd, y]);
  });
  if (points.length > 0) segments.push({ hasData, d: toPath(points) });

  return segments;
}

function toPath(points: [number, number][]) {
  return points
    .map(
      ([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(2)},${y.toFixed(2)}`,
    )
    .join(" ");
}

function formatBucketTime(date: Date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function SocHistoryChart({ buckets }: SocHistoryChartProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const selectedBucket = selected == null ? null : buckets[selected];
  const first = buckets[0];
  const last = buckets[buckets.length - 1];
  const n = buckets.length;
  const segments = buildStepSegments(buckets);

  return (
    <div className="select-none">
      <div className="flex h-5 items-baseline justify-between">
        <span className="text-13 text-muted-foreground">
          {selectedBucket && formatBucketTime(selectedBucket.bucket_start)}
        </span>
        {selectedBucket?.soc_percent != null && (
          <span className="text-13 font-semibold tabular-nums">
            {selectedBucket.soc_percent.toFixed(1)}%
            {!selectedBucket.has_data && (
              <span className="ml-1 font-normal text-muted-foreground">
                (no data)
              </span>
            )}
          </span>
        )}
      </div>

      <div className="mt-2 flex" style={{ height: CHART_HEIGHT }}>
        <div className="flex w-7 flex-col justify-between pb-px text-right text-10 text-muted-foreground tabular-nums">
          {[...Y_TICKS].reverse().map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>

        <div className="relative ml-1.5 flex-1">
          {Y_TICKS.map((t) => (
            <div
              key={t}
              className="absolute inset-x-0 h-px bg-border/50"
              style={{ bottom: `${t}%` }}
            />
          ))}

          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            className="absolute inset-0 h-full w-full overflow-visible"
          >
            {segments.map((seg, i) => (
              <path
                // biome-ignore lint/suspicious/noArrayIndexKey: segments are stable per render, keyed by order
                key={i}
                d={seg.d}
                fill="none"
                vectorEffect="non-scaling-stroke"
                strokeWidth={2}
                strokeLinejoin="round"
                className={
                  seg.hasData ? "stroke-foreground" : "stroke-muted-foreground"
                }
                strokeDasharray={seg.hasData ? undefined : "4 3"}
              />
            ))}
            {selectedBucket && selected != null && (
              <>
                <line
                  x1={((selected + 0.5) / n) * 100}
                  x2={((selected + 0.5) / n) * 100}
                  y1={0}
                  y2={100}
                  vectorEffect="non-scaling-stroke"
                  strokeWidth={1}
                  strokeDasharray="2 2"
                  className="stroke-muted-foreground/60"
                />
                <circle
                  cx={((selected + 0.5) / n) * 100}
                  cy={yFor(selectedBucket.soc_percent)}
                  r={3}
                  vectorEffect="non-scaling-stroke"
                  className="fill-background stroke-foreground"
                  strokeWidth={2}
                />
              </>
            )}
          </svg>

          <div className="absolute inset-0 flex">
            {buckets.map((bucket, i) => {
              const value = bucket.soc_percent;
              return (
                <button
                  key={bucket.bucket_start.toISOString()}
                  type="button"
                  onClick={() => setSelected(selected === i ? null : i)}
                  disabled={value == null}
                  aria-label={`${formatBucketTime(bucket.bucket_start)}: ${
                    value == null ? "no data" : `${value.toFixed(1)}%`
                  }`}
                  aria-pressed={selected === i}
                  className="h-full min-w-0 flex-1 disabled:cursor-default"
                />
              );
            })}
          </div>
        </div>
      </div>

      {first && last && (
        <div className="mt-1.5 ml-[34px] flex justify-between text-10 text-muted-foreground tabular-nums">
          <span>{formatBucketTime(first.bucket_start)}</span>
          <span>{formatBucketTime(last.bucket_start)}</span>
        </div>
      )}
    </div>
  );
}
