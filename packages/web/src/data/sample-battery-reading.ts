// Mirrors the "decoded" section of readings/2026-07-17_17-32-19.json.
// Stand-in until the dashboard reads live readings from a backend/API.
export interface BatteryReading {
  pack: {
    totalVoltageV: number;
    currentA: number;
    powerW: number;
    socPercent: number;
    remainingCapacityAh: number;
    mode: "charging" | "discharging" | "idle";
    cycles: number;
  };
  cellVoltagesV: number[];
  cellStats: {
    maxV: number;
    minV: number;
    averageV: number;
    deltaV: number;
  };
  temperature: {
    maxC: number;
    minC: number;
  };
  status: {
    cells: number;
    temperatureSensors: number;
    balancerActive: boolean;
    chargingMosfet: boolean;
    dischargingMosfet: boolean;
  };
  alarms: string;
  balancing: {
    balancingCells: number[];
    mosfetTemperatureC: number;
  };
  deviceModel: string;
}

export const sampleBatteryReading: BatteryReading = {
  pack: {
    totalVoltageV: 56.6,
    currentA: 17.6,
    powerW: 996.2,
    socPercent: 42.6,
    remainingCapacityAh: 21.3,
    mode: "charging",
    cycles: 2,
  },
  cellVoltagesV: [
    3.981, 3.983, 4.067, 4.063, 4.039, 4.042, 4.072, 4.068, 4.055, 4.045,
    4.066, 4.073, 4.06, 4.062,
  ],
  cellStats: {
    maxV: 4.073,
    minV: 3.981,
    averageV: 4.051,
    deltaV: 0.092,
  },
  temperature: {
    maxC: 33,
    minC: 33,
  },
  status: {
    cells: 14,
    temperatureSensors: 2,
    balancerActive: true,
    chargingMosfet: true,
    dischargingMosfet: true,
  },
  alarms: "none",
  balancing: {
    balancingCells: [1, 2, 3],
    mosfetTemperatureC: 34,
  },
  deviceModel: "226KF270201240",
};
