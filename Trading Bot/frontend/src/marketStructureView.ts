import { visibleZones } from "./terminalView.ts";
export const STRUCTURE_PERIODS = ["2m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"];

type Zone = Record<string, any>;

export function levelsForPeriod(zones: Zone[], period: string, perSide = 3): Zone[] {
 return visibleZones(zones, [period], perSide).map(z => ({...z, marker: z.label.split(" ")[1]}));
}
