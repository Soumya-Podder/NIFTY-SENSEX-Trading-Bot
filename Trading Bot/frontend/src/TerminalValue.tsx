import { useEffect, useRef, useState, type ReactNode } from "react";

// Flash only on an observed change; never interpolate a market price.
export function TerminalValue({ value, children, animate = true }: { value: number | null | undefined; children: ReactNode; animate?: boolean }) {
 const previous = useRef(value);
 const [direction, setDirection] = useState("");
 useEffect(() => {
  const before = previous.current;
  previous.current = value;
  if (!animate || value == null || before == null || !Number.isFinite(value) || !Number.isFinite(before) || value === before) {
   setDirection("");
   return;
  }
  setDirection(value > before ? "tick-up" : "tick-down");
  const timer = window.setTimeout(() => setDirection(""), 700);
  return () => window.clearTimeout(timer);
 }, [value, animate]);
 return <span className={`terminal-value ${direction}`}>{children}</span>;
}
