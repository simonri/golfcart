import { cn } from "@/lib/utils";

interface PackStatProps {
  label: string;
  value: string;
  unit?: string;
}

export function PackStat({ label, value, unit }: PackStatProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-13 text-muted-foreground">{label}</span>
      <span className="text-[17px] leading-tight font-semibold">
        {value}
        {unit && (
          <span className="ml-1 text-12 font-medium text-muted-foreground">
            {unit}
          </span>
        )}
      </span>
    </div>
  );
}

type InfoTone = "good" | "bad";

const TONE_CLASS: Record<InfoTone, string> = {
  good: "text-green-500",
  bad: "text-destructive",
};

interface InfoRowProps {
  label: string;
  value: string;
  tone?: InfoTone;
}

export function InfoRow({ label, value, tone }: InfoRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span
        className={cn(
          "text-right text-sm font-medium tabular-nums",
          tone && TONE_CLASS[tone],
        )}
      >
        {value}
      </span>
    </div>
  );
}
