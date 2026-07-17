import { createFileRoute } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { Moon, TriangleAlert, Zap } from "lucide-react";
import { CellVoltageChart } from "@/components/battery/cell-voltage-chart";
import { CircularGauge } from "@/components/battery/circular-gauge";
import { InfoRow, PackStat } from "@/components/battery/stat-tile";
import { Card } from "@/components/ui/card";
import type { BatteryReading } from "@/data/sample-battery-reading";
import { sampleBatteryReading } from "@/data/sample-battery-reading";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  component: HomePage,
});

const MODE: Record<
  BatteryReading["pack"]["mode"],
  { label: string; icon: LucideIcon; className: string }
> = {
  charging: {
    label: "Charging",
    icon: Zap,
    className: "bg-green-500/10 text-green-500",
  },
  discharging: {
    label: "Discharging",
    icon: Zap,
    className: "bg-blue-500/10 text-blue-400",
  },
  idle: {
    label: "Idle",
    icon: Moon,
    className: "bg-muted text-muted-foreground",
  },
};

function socTone(socPercent: number) {
  if (socPercent <= 15) {
    return { arc: "stroke-red-500", track: "stroke-red-500/15" };
  }
  if (socPercent <= 30) {
    return { arc: "stroke-amber-500", track: "stroke-amber-500/15" };
  }
  return { arc: "stroke-green-500", track: "stroke-green-500/15" };
}

function HomePage() {
  const {
    pack,
    cellVoltagesV,
    cellStats,
    temperature,
    status,
    alarms,
    balancing,
    deviceModel,
  } = sampleBatteryReading;

  const mode = MODE[pack.mode];
  const ModeIcon = mode.icon;
  const tone = socTone(pack.socPercent);
  const hasAlarm = alarms !== "none";

  const cellSummary = [
    { label: "Min", value: cellStats.minV.toFixed(3), unit: "V" },
    { label: "Avg", value: cellStats.averageV.toFixed(3), unit: "V" },
    { label: "Max", value: cellStats.maxV.toFixed(3), unit: "V" },
    {
      label: "Delta",
      value: String(Math.round(cellStats.deltaV * 1000)),
      unit: "mV",
    },
  ];

  return (
    <div className="min-h-dvh bg-background">
      <main className="mx-auto flex max-w-md flex-col gap-4 px-4 pt-[max(1.25rem,env(safe-area-inset-top))] pb-[max(2.5rem,env(safe-area-inset-bottom))]">
        <header className="flex flex-col items-center gap-0.5 pt-1">
          <h1 className="text-xl font-semibold">Battery</h1>
          <p className="text-13 text-muted-foreground">{deviceModel}</p>
        </header>

        {hasAlarm && (
          <Card className="flex-row items-center gap-3 border-none bg-destructive/10 p-4">
            <TriangleAlert className="size-5 shrink-0 text-destructive" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-destructive">
                Active alarm
              </p>
              <p className="text-13 text-muted-foreground">{alarms}</p>
            </div>
          </Card>
        )}

        <Card className="items-center gap-5 p-6">
          <CircularGauge
            value={pack.socPercent}
            size={176}
            arcClassName={tone.arc}
            trackClassName={tone.track}
          >
            <div className="flex flex-col items-center">
              <span className="text-[40px] leading-none font-bold">
                {pack.socPercent.toFixed(1)}
                <span className="ml-0.5 text-xl font-semibold text-muted-foreground">
                  %
                </span>
              </span>
              <span className="mt-1.5 text-12 text-muted-foreground">
                State of charge
              </span>
            </div>
          </CircularGauge>

          <span
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1 text-13 font-medium",
              mode.className,
            )}
          >
            <ModeIcon className="size-3.5" />
            {mode.label}
          </span>

          <div className="grid w-full grid-cols-2 gap-x-4 gap-y-4 border-t border-border pt-5">
            <PackStat
              label="Voltage"
              value={pack.totalVoltageV.toFixed(1)}
              unit="V"
            />
            <PackStat
              label="Current"
              value={pack.currentA.toFixed(1)}
              unit="A"
            />
            <PackStat label="Power" value={pack.powerW.toFixed(0)} unit="W" />
            <PackStat
              label="Remaining"
              value={pack.remainingCapacityAh.toFixed(1)}
              unit="Ah"
            />
          </div>
        </Card>

        <Card className="gap-4 p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Cell voltages</h2>
            {status.balancerActive && (
              <span className="flex items-center gap-1.5 text-13 font-medium text-green-500">
                <span className="size-1.5 rounded-full bg-green-500" />
                Balancing
              </span>
            )}
          </div>

          <CellVoltageChart
            voltagesV={cellVoltagesV}
            balancingCells={balancing.balancingCells}
          />

          <div className="grid grid-cols-4 divide-x divide-border rounded-lg border border-border">
            {cellSummary.map((stat) => (
              <div
                key={stat.label}
                className="flex flex-col items-center gap-0.5 py-2.5"
              >
                <span className="text-12 text-muted-foreground">
                  {stat.label}
                </span>
                <span className="text-sm font-semibold tabular-nums">
                  {stat.value}
                  <span className="ml-0.5 text-11 font-medium text-muted-foreground">
                    {stat.unit}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="gap-2 p-5">
          <h2 className="font-semibold">Details</h2>
          <div className="divide-y divide-border">
            <InfoRow
              label="Alarms"
              value={hasAlarm ? alarms : "None"}
              tone={hasAlarm ? "bad" : "good"}
            />
            <InfoRow
              label="Pack temperature"
              value={
                temperature.minC === temperature.maxC
                  ? `${temperature.maxC} °C`
                  : `${temperature.minC}–${temperature.maxC} °C`
              }
            />
            <InfoRow
              label="MOSFET temperature"
              value={`${balancing.mosfetTemperatureC} °C`}
            />
            <InfoRow
              label="Balancer"
              value={status.balancerActive ? "Active" : "Inactive"}
              tone={status.balancerActive ? "good" : undefined}
            />
            <InfoRow
              label="Charging MOSFET"
              value={status.chargingMosfet ? "On" : "Off"}
              tone={status.chargingMosfet ? "good" : undefined}
            />
            <InfoRow
              label="Discharging MOSFET"
              value={status.dischargingMosfet ? "On" : "Off"}
              tone={status.dischargingMosfet ? "good" : undefined}
            />
            <InfoRow label="Cycles" value={String(pack.cycles)} />
            <InfoRow label="Cells" value={String(status.cells)} />
            <InfoRow
              label="Temperature sensors"
              value={String(status.temperatureSensors)}
            />
          </div>
        </Card>
      </main>
    </div>
  );
}
