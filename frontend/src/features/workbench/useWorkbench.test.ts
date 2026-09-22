import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { api } from "../../api/client";
import type { ForecastResult, Revision, Run } from "../../api/types";
import { state } from "../../state";
import { defaultOverrides, statusLabels, useWorkbench } from "./useWorkbench";

vi.mock("../../api/client", () => ({
  api: {
    input: vi.fn(),
    runs: vi.fn(),
    run: vi.fn(),
    createRun: vi.fn(),
    resume: vi.fn(),
  },
}));

const result: ForecastResult = {
  currency: "CNY",
  unit: "元",
  profit_basis: "模拟管理口径利润",
  rule_version: "test-1",
  target_months: ["2026-09"],
  months: [],
  sources: [],
  warnings: [],
  sensitivity: [],
  scenario_totals: {},
  summary: {
    next_month_profit: "100.00",
    twelve_month_profit: "100.00",
    lifecycle_profit: "100.00",
    max_funding_gap: "0.00",
    ending_debt: "0.00",
    ending_receivables: "0.00",
    range_low: "80.00",
    range_high: "120.00",
  },
};
function revision(projectId: string): Revision {
  return {
    id: `revision-${projectId}`,
    project_id: projectId,
    version: 1,
    known_on: "2026-08-31",
    created_at: "2026-08-31T00:00:00Z",
    note: "测试输入",
    data: {
      phases: [],
      contracts: [],
      costs: [],
      actuals: [],
      actual_closed_through: "2026-08",
      assumptions: {
        opening_month: "2026-01",
        opening_cash: "0",
        monthly_overhead: "0",
        marketing_rate: "0",
        tax_rate: "0",
        down_payment_rate: "0.3",
        collection_lag: 3,
        expense_payment_lag: 0,
        loan_limit: "0",
        annual_interest_rate: "0",
        loan_draws: [],
        loan_repayments: [],
      },
    },
  };
}
function run(
  ids: string[],
  status: string,
  kind: Run["kind"] = "project",
): Run {
  return {
    id: `run-${ids.join("-")}`,
    kind,
    status,
    project_ids: ids,
    project_names: ids,
    created_at: "2026-08-31T09:00:00Z",
    forecast_origin: "2026-08-31",
    information_cutoff: "2026-08-31",
    scenario: "base",
    revision_ids: ids.map((id) => `revision-${id}`),
    attempt: 1,
    members: [],
    steps: [],
    result: status === "completed" ? result : null,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (cause: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

let wrapper: VueWrapper | undefined;
let sequence = 0;
let projectA = "";
let projectB = "";
function mountWorkbench() {
  let workbench!: ReturnType<typeof useWorkbench>;
  wrapper = mount(
    defineComponent({
      setup() {
        workbench = useWorkbench();
        return () => h("div");
      },
    }),
  );
  return workbench;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  vi.resetAllMocks();
  sequence++;
  projectA = `a-${sequence}`;
  projectB = `b-${sequence}`;
  Object.assign(state, {
    theme: "acg",
    mode: "project",
    projects: [],
    selectedProjectId: projectA,
    selectedProjectIds: [projectA, projectB],
    activeRun: null,
    overrides: {},
    drafts: {},
    forecastOrigin: "2026-08-31",
    informationCutoff: "2026-08-31",
    error: "",
    evidence: null,
  });
  vi.mocked(api.input).mockImplementation(async (id) => revision(id));
  vi.mocked(api.runs).mockResolvedValue([]);
});
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe("workbench persistent-run coordination", () => {
  it("keeps a waiting portfolio busy and polls through to completion without duplicate submission", async () => {
    state.mode = "portfolio";
    const waiting = run([projectA, projectB], "waiting", "portfolio");
    vi.mocked(api.createRun).mockResolvedValue(waiting);
    vi.mocked(api.run)
      .mockResolvedValueOnce(waiting)
      .mockResolvedValueOnce({ ...waiting, status: "completed", result });
    const workbench = mountWorkbench();
    await flushPromises();

    await workbench.generate();
    await flushPromises();
    expect(statusLabels.waiting).toBe("等待子项目");
    expect(workbench.busy.value).toBe(true);
    expect(workbench.result.value).toBeNull();
    await workbench.generate();
    expect(api.createRun).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1500);
    expect(workbench.currentRun.value?.status).toBe("completed");
    expect(workbench.result.value?.summary.twelve_month_profit).toBe("100.00");
    expect(workbench.busy.value).toBe(false);
    await vi.advanceTimersByTimeAsync(15000);
    expect(api.run).toHaveBeenCalledTimes(2);
  });

  it.each(["failed", "incomplete", "interrupted"])(
    "stops polling at %s without filling in a missing result",
    async (terminal) => {
      const pending = run([projectA], "queued");
      vi.mocked(api.runs).mockResolvedValue([pending]);
      vi.mocked(api.run).mockResolvedValue({ ...pending, status: terminal });
      const workbench = mountWorkbench();
      await flushPromises();

      expect(workbench.currentRun.value?.status).toBe(terminal);
      expect(workbench.result.value).toBeNull();
      expect(workbench.busy.value).toBe(false);
      await vi.advanceTimersByTimeAsync(10000);
      expect(api.run).toHaveBeenCalledTimes(1);
    },
  );

  it("rejects late input and history responses from a previously selected project", async () => {
    const oldInput = deferred<Revision>();
    const oldRuns = deferred<Run[]>();
    vi.mocked(api.input).mockImplementation((id) =>
      id === projectA ? oldInput.promise : Promise.resolve(revision(id)),
    );
    vi.mocked(api.runs).mockImplementation((id) =>
      id === projectA
        ? oldRuns.promise
        : Promise.resolve([run([projectB], "completed")]),
    );
    const workbench = mountWorkbench();

    state.selectedProjectId = projectB;
    await nextTick();
    await flushPromises();
    expect(workbench.currentRevision.value?.project_id).toBe(projectB);
    expect(workbench.resultRun.value?.project_ids).toEqual([projectB]);

    oldInput.resolve(revision(projectA));
    oldRuns.resolve([run([projectA], "completed")]);
    await flushPromises();
    expect(workbench.currentRevision.value?.project_id).toBe(projectB);
    expect(workbench.currentRun.value?.project_ids).toEqual([projectB]);
    expect(workbench.loading.value).toBe(false);
  });

  it("does not show another project result during a scope switch or apply its late polling response", async () => {
    const oldPoll = deferred<Run>();
    vi.mocked(api.runs).mockImplementation(async (id) => [
      run([id!], id === projectA ? "queued" : "completed"),
    ]);
    vi.mocked(api.run).mockReturnValue(oldPoll.promise);
    const workbench = mountWorkbench();
    await flushPromises();

    state.selectedProjectId = projectB;
    expect(workbench.currentRun.value).toBeNull();
    expect(workbench.resultRun.value).toBeNull();
    await nextTick();
    await flushPromises();
    oldPoll.resolve(run([projectA], "completed"));
    await flushPromises();
    expect(workbench.resultRun.value?.project_ids).toEqual([projectB]);

    state.selectedProjectId = projectA;
    expect(workbench.resultRun.value).toBeNull();
  });

  it("ignores an older waiting response after a manual refresh already observed completion", async () => {
    const pending = run([projectA, projectB], "waiting", "portfolio");
    const oldPoll = deferred<Run>();
    state.mode = "portfolio";
    vi.mocked(api.runs).mockResolvedValue([pending]);
    vi.mocked(api.run)
      .mockReturnValueOnce(oldPoll.promise)
      .mockResolvedValueOnce({ ...pending, status: "completed", result });
    const workbench = mountWorkbench();
    await flushPromises();

    await workbench.refreshStatus();
    oldPoll.resolve(pending);
    await flushPromises();
    expect(workbench.currentRun.value?.status).toBe("completed");
    await vi.advanceTimersByTimeAsync(10000);
    expect(api.run).toHaveBeenCalledTimes(2);
  });

  it("reuses the idempotency key after an uncertain response but issues a new key for changed input", async () => {
    vi.mocked(api.createRun).mockRejectedValue(new Error("连接中断"));
    const workbench = mountWorkbench();
    await flushPromises();
    await workbench.generate();
    await workbench.generate();
    const calls = vi.mocked(api.createRun).mock.calls;
    expect(calls[1]?.[1]).toBe(calls[0]?.[1]);
    state.overrides[projectA] = { ...defaultOverrides(), collection_delay: 2 };
    await workbench.generate();
    expect(calls[2]?.[1]).not.toBe(calls[1]?.[1]);
    expect(calls[2]?.[0].project_ids).toEqual([projectA]);
    expect(calls[2]?.[0].base_versions).toEqual({ [projectA]: 1 });
  });

  it("keeps drafts and displayed run on theme change without requests or calculation", async () => {
    vi.mocked(api.runs).mockResolvedValue([run([projectA], "completed")]);
    const workbench = mountWorkbench();
    await flushPromises();
    state.overrides[projectA] = { ...defaultOverrides(), price_change: "0.05" };
    workbench.markDirty();
    const beforeId = workbench.resultRun.value?.id;

    state.theme = "minimal";
    await nextTick();
    expect(state.overrides[projectA]?.price_change).toBe("0.05");
    expect(workbench.resultRun.value?.id).toBe(beforeId);
    expect(workbench.dirtySinceResult.value).toBe(true);
    expect(api.input).toHaveBeenCalledTimes(1);
    expect(api.runs).toHaveBeenCalledTimes(1);
    expect(api.createRun).not.toHaveBeenCalled();
  });

  it("stops scheduling polling when leaving the workbench while preserving the task reference", async () => {
    const waiting = run([projectA, projectB], "waiting", "portfolio");
    state.mode = "portfolio";
    vi.mocked(api.runs).mockResolvedValue([waiting]);
    vi.mocked(api.run).mockResolvedValue(waiting);
    mountWorkbench();
    await flushPromises();
    wrapper?.unmount();
    wrapper = undefined;
    await vi.advanceTimersByTimeAsync(10000);
    expect(api.run).toHaveBeenCalledTimes(1);
    expect(state.activeRun?.id).toBe(waiting.id);
  });
});
