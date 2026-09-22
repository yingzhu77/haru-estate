import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, shallowMount, type VueWrapper } from "@vue/test-utils";
import { api } from "../../api/client";
import type { Run } from "../../api/types";
import RunDetailView from "./RunDetailView.vue";

vi.mock("../../api/client", () => ({
  api: { run: vi.fn(), input: vi.fn(), resume: vi.fn() },
}));
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { id: "portfolio-1" } }),
}));
const base: Run = {
  id: "portfolio-1",
  kind: "portfolio",
  status: "waiting",
  created_at: "2026-09-01",
  forecast_origin: "2026-08-31",
  information_cutoff: "2026-08-31",
  scenario: "base",
  project_ids: ["p1"],
  project_names: ["模拟项目"],
  revision_ids: ["frozen-r1"],
  attempt: 1,
  members: [
    {
      project_id: "p1",
      project_name: "模拟项目",
      run_id: "child-frozen",
      revision_id: "frozen-r1",
      status: "running",
    },
  ],
  steps: [],
};
let wrapper: VueWrapper;
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  vi.mocked(api.run).mockResolvedValue(base);
  vi.mocked(api.input).mockResolvedValue({
    id: "frozen-r1",
    project_id: "p1",
    version: 1,
    known_on: "2026-08-31",
    created_at: "2026-09-01",
    note: "frozen",
    data: {
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
      },
    },
  });
});
afterEach(() => {
  wrapper?.unmount();
  vi.useRealTimers();
});
describe("persistent run detail", () => {
  it("polls waiting portfolios, reads the frozen revision, then stops at a terminal state", async () => {
    wrapper = shallowMount(RunDetailView, {
      global: {
        renderStubDefaultSlot: true,
        stubs: {
          RouterLink: true,
          ElButton: true,
          ElAlert: true,
          ElTag: true,
          ElSkeleton: true,
          ElDescriptions: true,
          ElDescriptionsItem: true,
          ElTable: { template: "<div />" },
          ElTableColumn: true,
          ElEmpty: true,
          ElTimeline: true,
          ElTimelineItem: true,
        },
      },
    });
    await flushPromises();
    expect(api.input).toHaveBeenCalledWith("p1", "frozen-r1");
    expect(wrapper.text()).toContain("等待成员完成");
    vi.mocked(api.run).mockResolvedValue({ ...base, status: "incomplete" });
    await vi.advanceTimersByTimeAsync(1500);
    await flushPromises();
    expect(api.run).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(3000);
    expect(api.run).toHaveBeenCalledTimes(2);
    expect(api.input).toHaveBeenCalledTimes(1);
  });
});
