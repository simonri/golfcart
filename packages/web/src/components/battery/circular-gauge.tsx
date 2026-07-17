import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface CircularGaugeProps {
  value: number;
  size?: number;
  strokeWidth?: number;
  arcClassName?: string;
  trackClassName?: string;
  children?: ReactNode;
}

export function CircularGauge({
  value,
  size = 180,
  strokeWidth = 12,
  arcClassName = "stroke-green-500",
  trackClassName = "stroke-green-500/15",
  children,
}: CircularGaugeProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(Math.max(value, 0), 100);
  const offset = circumference * (1 - clamped / 100);

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-90"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          className={trackClassName}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={cn(
            "transition-[stroke-dashoffset] duration-500 ease-out",
            arcClassName,
          )}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        {children}
      </div>
    </div>
  );
}
