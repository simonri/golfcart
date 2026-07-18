import type { SocHistoryBucketSchema } from "@bessel/client";
import { useState } from "react";
import { cn } from "@/lib/utils";

const CHART_HEIGHT = 96;

interface SocHistoryChartProps {
  buckets: SocHistoryBucketSchema[];
}

function socBarTone(socPercent: number) {
  if (socPercent <= 15) return "bg-red-500/80";
  if (socPercent <= 30) return "bg-amber-500/80";
  return "bg-green-500/80";
}

function formatBucketTime(date: Date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function SocHistoryChart({ buckets }: SocHistoryChartProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const selectedBucket = selected == null ? null : buckets[selected];
  const first = buckets[0];
  const last = buckets[buckets.length - 1];

  return (
    <div className="select-none">
      <div className="flex h-5 items-baseline justify-between">
        <span className="text-13 text-muted-foreground">
          {selectedBucket
            ? formatBucketTime(selectedBucket.bucket_start)
            : "Tap a bar to inspect"}
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

      <div
        className="mt-2 flex items-end gap-[3px]"
        style={{ height: CHART_HEIGHT }}
      >
        {buckets.map((bucket, i) => {
          const isSelected = selected === i;
          const value = bucket.soc_percent;
          const height = value == null ? 2 : Math.max(value, 2);
          return (
            <button
              key={bucket.bucket_start.toISOString()}
              type="button"
              onClick={() => setSelected(isSelected ? null : i)}
              disabled={value == null}
              aria-label={`${formatBucketTime(bucket.bucket_start)}: ${
                value == null ? "no data" : `${value.toFixed(1)}%`
              }`}
              aria-pressed={isSelected}
              className="flex h-full min-w-0 flex-1 items-end justify-center disabled:cursor-default"
            >
              <div
                className={cn(
                  "w-full rounded-t-[3px] transition-colors",
                  value == null
                    ? "bg-muted"
                    : !bucket.has_data
                      ? "bg-muted-foreground/30"
                      : socBarTone(value),
                  isSelected && "ring-2 ring-inset ring-foreground/60",
                )}
                style={{ height: `${height}%` }}
              />
            </button>
          );
        })}
      </div>

      {first && last && (
        <div className="mt-1.5 flex justify-between text-10 text-muted-foreground tabular-nums">
          <span>{formatBucketTime(first.bucket_start)}</span>
          <span>{formatBucketTime(last.bucket_start)}</span>
        </div>
      )}
    </div>
  );
}
