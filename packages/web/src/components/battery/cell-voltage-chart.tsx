import { useState } from "react";
import { cn } from "@/lib/utils";

const CHART_HEIGHT = 132;
const TICK_STEPS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1];

interface CellVoltageChartProps {
  voltagesV: number[];
  balancingCells: number[];
}

function computeScale(voltagesV: number[]) {
  const min = Math.min(...voltagesV);
  const max = Math.max(...voltagesV);
  const span = Math.max(max - min, 0.005);
  const step = TICK_STEPS.find((s) => span / s <= 4) ?? 1;

  let lo = Math.floor(min / step) * step;
  if (min - lo < step / 4) lo -= step;
  let hi = Math.ceil(max / step) * step;
  if (hi - max < step / 10) hi += step;

  const ticks: number[] = [];
  for (let t = lo; t <= hi + step / 2; t += step) {
    ticks.push(Math.round(t * 1000) / 1000);
  }
  return ticks;
}

export function CellVoltageChart({
  voltagesV,
  balancingCells,
}: CellVoltageChartProps) {
  const [selected, setSelected] = useState<number | null>(null);

  const ticks = computeScale(voltagesV);
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const pct = (v: number) => ((v - lo) / (hi - lo)) * 100;
  const selectedV = selected == null ? null : voltagesV[selected - 1];

  return (
    <div className="select-none">
      <div className="flex h-5 items-baseline justify-between">
        <span className="text-13 text-muted-foreground">
          {selected != null && `Cell ${selected}`}
        </span>
        {selectedV != null && (
          <span className="text-13 font-semibold tabular-nums">
            {selectedV.toFixed(3)} V
          </span>
        )}
      </div>

      <div className="relative mt-2" style={{ height: CHART_HEIGHT }}>
        {ticks.map((t) => (
          <div
            key={t}
            className="absolute inset-x-0 flex translate-y-1/2 items-center"
            style={{ bottom: `${pct(t)}%` }}
          >
            <div
              className={cn(
                "h-px flex-1",
                t === lo ? "bg-border" : "bg-border/50",
              )}
            />
            <span className="w-8 pl-1 text-right text-10 text-muted-foreground tabular-nums">
              {t.toFixed(2)}
            </span>
          </div>
        ))}

        <div className="absolute inset-y-0 left-0 right-9 flex items-end gap-0.5">
          {voltagesV.map((v, i) => {
            const cell = i + 1;
            const isSelected = selected === cell;
            return (
              <button
                key={cell}
                type="button"
                onClick={() => setSelected(isSelected ? null : cell)}
                aria-label={`Cell ${cell}: ${v.toFixed(3)} volts`}
                aria-pressed={isSelected}
                className="flex h-full min-w-0 flex-1 items-end justify-center"
              >
                <div
                  className={cn(
                    "w-full max-w-2.5 rounded-t-[4px] transition-colors",
                    isSelected
                      ? "bg-green-600 dark:bg-green-400"
                      : selected != null
                        ? "bg-green-500/35"
                        : "bg-green-500/80",
                  )}
                  style={{ height: `${Math.max(pct(v), 2)}%` }}
                />
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-1.5 mr-9 flex gap-0.5">
        {voltagesV.map((_, i) => {
          const cell = i + 1;
          const isBalancing = balancingCells.includes(cell);
          const showNumber =
            voltagesV.length <= 12 || cell % 2 === 1 || selected === cell;
          return (
            <div
              key={cell}
              className="flex min-w-0 flex-1 flex-col items-center gap-1"
            >
              <span
                className={cn(
                  "text-10 tabular-nums",
                  selected === cell
                    ? "font-semibold text-foreground"
                    : "text-muted-foreground",
                  !showNumber && "invisible",
                )}
              >
                {cell}
              </span>
              <span
                className={cn(
                  "size-1 rounded-full",
                  isBalancing ? "bg-green-500" : "bg-transparent",
                )}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
