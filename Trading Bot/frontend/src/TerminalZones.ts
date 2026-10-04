import type { Row } from "./terminalView";

/** Chart primitive shares the chart's coordinate system during pan, zoom and resize. */
export class TerminalZones {
 chart: any; series: any; request: () => void = () => {};
 zones: Row[] = []; times: number[] = []; periodSeconds = 300;
 attached({chart, series, requestUpdate}: any) { this.chart = chart; this.series = series; this.request = requestUpdate; }
 detached() { this.chart = null; this.series = null; }
 update(zones: Row[], times: number[], periodSeconds = 300) { this.zones = zones; this.times = times; this.periodSeconds = periodSeconds; this.request(); }
 paneViews() { return [{zOrder: () => "bottom" as const, renderer: () => ({draw: (target: any) => {
  if (!this.chart || !this.series) return;
  target.useMediaCoordinateSpace(({context: ctx, mediaSize}: any) => {
   const labels: any[] = [];
   for (const zone of this.zones) {
    const known = Date.parse(zone.available_at)/1000;
    const index = this.times.findIndex(t => t >= known);
    if (!this.times.length) continue;
    const last = this.times[this.times.length-1];
    if (index < 0 && known > last+this.periodSeconds) continue;
    const x = known <= this.times[0] ? 0 : index >= 0 ? this.chart.timeScale().timeToCoordinate(this.times[index]) :
     this.chart.timeScale().logicalToCoordinate(this.times.length-1+(known-last)/this.periodSeconds);
    const upper = this.series.priceToCoordinate(zone.upper), lower = this.series.priceToCoordinate(zone.lower);
    if (x === null || upper === null || lower === null || lower < 0 || upper > mediaSize.height) continue;
    // These are current reference zones, extended across the viewport. The
    // confirmation marker and details retain when each zone first became known.
    const left = 0, width = mediaSize.width;
    const rgb = zone.relation === "SUPPORT" ? "16,185,129" : zone.relation === "RESISTANCE" ? "244,63,94" : "139,92,246";
    ctx.fillStyle = `rgba(${rgb},0.06)`; ctx.fillRect(left, upper, width, Math.max(2, lower-upper));
    ctx.strokeStyle = `rgba(${rgb},0.8)`; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
    ctx.strokeRect(left, upper, width, Math.max(2, lower-upper)); ctx.setLineDash([]);
    if (x > 0 && x < width) {
     ctx.beginPath(); ctx.moveTo(x, upper-4); ctx.lineTo(x, lower+4); ctx.stroke();
    }
    labels.push({text: `${zone.label} · ${zone.price.toFixed(2)}`, color: `rgb(${rgb})`, y: Math.max(14, Math.min(mediaSize.height-5, upper)), anchor: Math.max(0, upper), count: 1});
   }
   labels.sort((a, b) => a.y-b.y);
   // Consolidate only canvas labels, never the underlying price bands or evidence.
   // Dense selections must not push labels outside the pane.
   const capacity = Math.max(1, Math.floor((mediaSize.height-19)/20)+1);
   while (labels.length > 1) {
    let closest = 0;
    for (let i = 1; i < labels.length-1; i++) if (labels[i+1].y-labels[i].y < labels[closest+1].y-labels[closest].y) closest = i;
    if (labels.length <= capacity && labels[closest+1].y-labels[closest].y >= 20) break;
    labels[closest].count += labels[closest+1].count; labels.splice(closest+1, 1);
   }
   labels.forEach((l, i) => { if (i) l.y = Math.max(l.y, labels[i-1].y+20); });
   for (let i = labels.length-1; i >= 0; i--) labels[i].y = Math.min(labels[i].y, i === labels.length-1 ? mediaSize.height-5 : labels[i+1].y-20);
   ctx.font = "11px system-ui";
   for (const label of labels) {
    const text = label.text+(label.count > 1 ? ` +${label.count-1}` : "");
    const width = Math.min(mediaSize.width-8, ctx.measureText(text).width+10), left = mediaSize.width-width-4;
    ctx.strokeStyle = label.color; ctx.beginPath(); ctx.moveTo(left-10, label.anchor); ctx.lineTo(left, label.y-5); ctx.stroke();
    ctx.fillStyle = document.documentElement.dataset.theme === "light" ? "rgba(255,255,255,.94)" : "rgba(0,0,0,.94)";
    ctx.fillRect(left, label.y-12, width, 15); ctx.fillStyle = label.color; ctx.fillText(text, left+5, label.y, width-10);
   }
  });
 }})}]; }
}
