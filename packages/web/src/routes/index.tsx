import type { HistoryPeriod } from "@golfcart/client";
import {
  createReadingV1ReadingsPostMutation,
  getSocHistoryV1ReadingsSocHistoryGetOptions,
} from "@golfcart/client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { BluetoothOff, Loader2, Moon, TriangleAlert, Zap } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { CellVoltageChart } from "@/components/battery/cell-voltage-chart";
import { CircularGauge } from "@/components/battery/circular-gauge";
import { SocHistoryChart } from "@/components/battery/soc-history-chart";
import { InfoRow, PackStat } from "@/components/battery/stat-tile";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

const HISTORY_REFETCH_INTERVAL_MS = 60_000;

export const Route = createFileRoute("/")({
  component: HomePage,
});

const MODE: Record<
  string,
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

function captureErrorMessage(error: unknown): string {
  if (
    error &&
    typeof error === "object" &&
    "detail" in error &&
    typeof error.detail === "string"
  ) {
    return error.detail;
  }
  return "The BMS is unreachable. Make sure it's powered and in range.";
}

function CenteredMessage({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-background px-6 text-center">
      {children}
    </div>
  );
}

function HomePage() {
  const capture = useMutation(createReadingV1ReadingsPostMutation());
  const triggered = useRef(false);
  const [historyPeriod, setHistoryPeriod] = useState<HistoryPeriod>("1h");
  const history = useQuery({
    ...getSocHistoryV1ReadingsSocHistoryGetOptions({
      query: { period: historyPeriod },
    }),
    refetchInterval: HISTORY_REFETCH_INTERVAL_MS,
  });

  useEffect(() => {
    if (triggered.current) return;
    triggered.current = true;
    capture.mutate({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (capture.isError) {
    return (
      <CenteredMessage>
        <BluetoothOff className="size-8 text-destructive" />
        <p className="text-sm font-medium">Couldn't reach the battery</p>
        <p className="max-w-xs text-13 text-muted-foreground">
          {captureErrorMessage(capture.error)}
        </p>
        <Button variant="outline" onClick={() => capture.mutate({})}>
          Try again
        </Button>
      </CenteredMessage>
    );
  }

  if (!capture.data) {
    return (
      <CenteredMessage>
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Reading battery over Bluetooth…
        </p>
      </CenteredMessage>
    );
  }

  const reading = capture.data;
  const mode = MODE[reading.mode] ?? MODE.idle;
  const ModeIcon = mode.icon;
  const tone = socTone(reading.soc_percent);
  const hasAlarm = reading.has_alarms;
  const alarmMessages = reading.alarm_messages ?? [];
  const balancingCells = reading.balancing?.balancing_cells ?? [];
  const mosfetTemperatureC = reading.balancing?.mosfet_temperature_c;

  const cellSummary = [
    { label: "Min", value: reading.cell_voltage_min_v.toFixed(3), unit: "V" },
    { label: "Avg", value: reading.cell_voltage_avg_v.toFixed(3), unit: "V" },
    { label: "Max", value: reading.cell_voltage_max_v.toFixed(3), unit: "V" },
    {
      label: "Delta",
      value: String(Math.round(reading.cell_voltage_delta_v * 1000)),
      unit: "mV",
    },
  ];

  return (
    <div className="min-h-dvh bg-background">
      <main className="mx-auto flex max-w-md flex-col gap-4 px-4 pt-[max(1.25rem,env(safe-area-inset-top))] pb-[max(2.5rem,env(safe-area-inset-bottom))]">
        <header className="flex flex-col items-center gap-0.5 pt-1">
          <h1 className="text-xl font-semibold">Battery</h1>
          <p className="text-13 text-muted-foreground">
            {reading.device_model ?? reading.device_name ?? "Unknown device"}
          </p>
        </header>

        {hasAlarm && (
          <Card className="flex-row items-start gap-3 border-none bg-destructive/10 p-4">
            <TriangleAlert className="mt-0.5 size-5 shrink-0 text-destructive" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-destructive">
                {alarmMessages.length > 0
                  ? "Active alarm"
                  : "Unrecognized alarm"}
              </p>
              {alarmMessages.length > 0 ? (
                <ul className="text-13 text-muted-foreground">
                  {alarmMessages.map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-13 text-muted-foreground">
                  The BMS reports an alarm that doesn't match a known message.
                </p>
              )}
            </div>
          </Card>
        )}

        <Card className="items-center gap-5 p-6">
          <CircularGauge
            value={reading.soc_percent}
            size={176}
            arcClassName={tone.arc}
            trackClassName={tone.track}
          >
            <div className="flex flex-col items-center">
              <span className="text-[40px] leading-none font-bold">
                {reading.soc_percent.toFixed(1)}
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
              value={reading.voltage_v.toFixed(1)}
              unit="V"
            />
            <PackStat
              label="Current"
              value={reading.current_a.toFixed(1)}
              unit="A"
            />
            <PackStat
              label="Power"
              value={reading.power_w.toFixed(0)}
              unit="W"
            />
            <PackStat
              label="Remaining"
              value={reading.remaining_capacity_ah.toFixed(1)}
              unit="Ah"
            />
          </div>
        </Card>

        <Card className="gap-4 p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">History</h2>
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={historyPeriod}
              onValueChange={(value) => {
                if (value) setHistoryPeriod(value as HistoryPeriod);
              }}
            >
              <ToggleGroupItem value="5m">5m</ToggleGroupItem>
              <ToggleGroupItem value="1h">1h</ToggleGroupItem>
            </ToggleGroup>
          </div>

          {history.data ? (
            <SocHistoryChart buckets={history.data.buckets} />
          ) : (
            <div
              className="animate-pulse rounded-lg bg-muted"
              style={{ height: 96 }}
            />
          )}
        </Card>

        <Card className="gap-4 p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Cell voltages</h2>
            {reading.balancer_active && (
              <span className="flex items-center gap-1.5 text-13 font-medium text-green-500">
                <span className="size-1.5 rounded-full bg-green-500" />
                Balancing
              </span>
            )}
          </div>

          <CellVoltageChart
            voltagesV={reading.cell_voltages}
            balancingCells={balancingCells}
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
              value={
                alarmMessages.length > 0
                  ? alarmMessages.join(", ")
                  : hasAlarm
                    ? "Unrecognized"
                    : "None"
              }
              tone={hasAlarm ? "bad" : "good"}
            />
            <InfoRow
              label="Pack temperature"
              value={
                reading.temperature_min_c === reading.temperature_max_c
                  ? `${reading.temperature_max_c} °C`
                  : `${reading.temperature_min_c}–${reading.temperature_max_c} °C`
              }
            />
            {mosfetTemperatureC != null && (
              <InfoRow
                label="MOSFET temperature"
                value={`${mosfetTemperatureC} °C`}
              />
            )}
            <InfoRow
              label="Balancer"
              value={reading.balancer_active ? "Active" : "Inactive"}
              tone={reading.balancer_active ? "good" : undefined}
            />
            <InfoRow
              label="Charging MOSFET"
              value={reading.charging_mosfet ? "On" : "Off"}
              tone={reading.charging_mosfet ? "good" : undefined}
            />
            <InfoRow
              label="Discharging MOSFET"
              value={reading.discharging_mosfet ? "On" : "Off"}
              tone={reading.discharging_mosfet ? "good" : undefined}
            />
            <InfoRow label="Cycles" value={String(reading.cycles)} />
            <InfoRow label="Cells" value={String(reading.cell_count)} />
            <InfoRow
              label="Temperature sensors"
              value={String(reading.temperature_sensor_count)}
            />
          </div>
        </Card>

        <Button
          variant="outline"
          onClick={() => capture.mutate({})}
          disabled={capture.isPending}
        >
          {capture.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            "Capture again"
          )}
        </Button>
      </main>
    </div>
  );
}
