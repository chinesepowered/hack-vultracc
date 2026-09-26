import type { Api } from "./types";
import { realApi } from "./real";

export { ApiError } from "./real";

/** The active API implementation. Swapped for the in-browser mock when VITE_MOCK=1. */
export let api: Api = realApi;

export const isMock: boolean = __MOCK__;

export async function initApi(): Promise<void> {
  if (__MOCK__) {
    const mod = await import("@/mocks/mockApi");
    api = mod.createMockApi();
  }
}
