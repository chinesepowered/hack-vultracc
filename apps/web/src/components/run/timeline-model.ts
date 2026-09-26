import type { RunEvent } from "@/api/types";

export interface StepItem {
  kind: "step";
  key: string;
  n: number | null;
  tool: string;
  call: RunEvent;
  result?: RunEvent;
  thought?: RunEvent;
  llm?: RunEvent;
  validation?: RunEvent;
}

export type TimelineItem =
  | StepItem
  | { kind: "run_started" | "untrusted" | "sandbox" | "stored" | "sandbox_destroyed" | "run_finished" | "stopped" | "replay_step" | "replay_compared"; key: string; ev: RunEvent };

export interface TimelineModel {
  items: TimelineItem[];
  steps: StepItem[];
  llmCalls: number;
  tokensIn: number;
  tokensOut: number;
  lastEvent: RunEvent | null;
  /** The agent is waiting for the model (last thing that happened was a result, not a call). */
  thinking: boolean;
  /** A tool call is running in the sandbox right now. */
  executing: StepItem | null;
}

const SIMPLE: Record<string, TimelineItem["kind"]> = {
  run_started: "run_started",
  untrusted_text: "untrusted",
  sandbox_created: "sandbox",
  stored: "stored",
  sandbox_destroyed: "sandbox_destroyed",
  run_finished: "run_finished",
  stopped: "stopped",
  replay_step: "replay_step",
  replay_compared: "replay_compared",
};

export function buildTimeline(events: RunEvent[]): TimelineModel {
  const items: TimelineItem[] = [];
  const steps: StepItem[] = [];
  let thought: RunEvent | undefined;
  let llm: RunEvent | undefined;
  let llmCalls = 0;
  let tokensIn = 0;
  let tokensOut = 0;

  for (const ev of events) {
    const simple = SIMPLE[ev.type];
    if (simple) {
      items.push({ kind: simple, key: `${ev.type}-${ev.seq}`, ev } as TimelineItem);
      continue;
    }
    switch (ev.type) {
      case "llm":
        llm = ev;
        llmCalls += 1;
        tokensIn += ev.payload?.tokens_in ?? 0;
        tokensOut += ev.payload?.tokens_out ?? 0;
        break;
      case "thought":
        thought = ev;
        break;
      case "tool_call": {
        const step: StepItem = {
          kind: "step",
          key: `step-${ev.seq}`,
          n: ev.payload?.n ?? null,
          tool: ev.payload?.tool ?? "tool",
          call: ev,
          thought,
          llm,
        };
        thought = undefined;
        llm = undefined;
        steps.push(step);
        items.push(step);
        break;
      }
      case "tool_result": {
        const n = ev.payload?.n ?? null;
        const target = [...steps].reverse().find((s) => !s.result && s.n === n && s.tool === (ev.payload?.tool ?? s.tool));
        if (target) target.result = ev;
        break;
      }
      case "validation": {
        const target = [...steps].reverse().find((s) => s.tool === "finish" && !s.validation) ?? steps[steps.length - 1];
        if (target) target.validation = ev;
        break;
      }
      default:
        break;
    }
  }

  // The control plane scans inputs before the agent starts, so its warning can precede "run started"; tell the story in order.
  const startIdx = items.findIndex((it) => it.kind === "run_started");
  if (startIdx > 0 && items.slice(0, startIdx).every((it) => it.kind === "untrusted")) {
    const [start] = items.splice(startIdx, 1);
    items.unshift(start);
  }

  const lastEvent = events.length ? events[events.length - 1] : null;
  const lastStep = steps[steps.length - 1];
  const executing = lastStep && lastStep.tool !== "finish" && !lastStep.result ? lastStep : null;
  const ended = events.some((e) => e.type === "run_finished" || e.type === "stopped" || e.type === "sandbox_destroyed");
  const thinking =
    !ended &&
    !executing &&
    !!lastEvent &&
    ["sandbox_created", "tool_result", "llm", "thought", "progress", "untrusted_text", "validation"].includes(lastEvent.type) &&
    !(lastStep?.tool === "finish" && !lastStep.validation);

  return { items, steps, llmCalls, tokensIn, tokensOut, lastEvent, thinking, executing };
}
