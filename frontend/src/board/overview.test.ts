import { describe, expect, it } from "vitest";
import { addExpansion, bandsOf, clusterOfFile, linkLines, linkedTo, stepCluster } from "./overview";
import type { Overview } from "./types";

const c = (id: string, name: string, level: number | null, over: Partial<Overview["clusters"][0]> = {}) => ({
  id, name, level, also: [], risk: null, test: false, files: [], changed: 1, flows: 0, findings: 0, finding_ids: [], nodes: [], ...over,
});
const ov: Overview = {
  about: { intent: "", intent_source: "template", why: [], cls: [], tree: [], drift: [] },
  clusters: [c("C1", "svc/logger", 2, { files: ["//d/svc/logger.c"] }), c("C2", "drv/uart", 1, { also: [0] }),
             c("C3", "app/telemetry", 3), c("C4", "tests", null, { test: true })],
  links: [{ src: "C2", dst: "C1", calls: 22, fields: 3 }, { src: "C1", dst: "C3", calls: 9, fields: 0 },
          { src: "C4", dst: "C2", calls: 1, fields: 0 }],
  layers: [{ level: 3, name: "app" }, { level: 2, name: "service" }, { level: 1, name: "driver" }, { level: 0, name: "hal" },
           { level: -1, name: "other" }],
  totals: { files: 9, clusters: 4, flows: 20, findings: 5, changed: 12 }, merged_over_limit: 0,
};

describe("bandsOf", () => {
  it("puts each cluster in its layer, top layer first, unlayered last, and drops empty layers", () => {
    expect(bandsOf(ov).map((b) => [b.name, b.clusters.map((x) => x.id)])).toEqual(
      [["app", ["C3"]], ["service", ["C1"]], ["driver", ["C2"]], ["other", ["C4"]]]);
  });
});

describe("linkLines", () => {
  it("says what a cluster calls and what calls it, in words", () => {
    expect(linkLines(ov, "C1")).toEqual(["← drv/uart: 22 calls, 3 shared fields", "→ app/telemetry: 9 calls"]);
    expect(linkLines(ov, "C3")).toEqual(["← svc/logger: 9 calls"]);
  });
  it("keeps it short on a phone", () => {
    expect(linkLines(ov, "C2", 1)).toEqual(["→ svc/logger: 22 calls, 3 shared fields"]);
  });
});

describe("linkedTo", () => {
  it("is every cluster linked either way", () => {
    expect([...linkedTo(ov, "C2")].sort()).toEqual(["C1", "C4"]);
  });
});

describe("stepCluster", () => {
  it("moves through the clusters in risk order, wrapping", () => {
    expect(stepCluster(ov, "C1", 1)).toBe("C2");
    expect(stepCluster(ov, "C4", 1)).toBe("C1");
    expect(stepCluster(ov, "C1", -1)).toBe("C4");
  });
});

describe("clusterOfFile", () => {
  it("finds the cluster whose changed code is in a file", () => {
    expect(clusterOfFile(ov, "//d/svc/logger.c")).toBe("C1");
    expect(clusterOfFile(ov, "//d/none.c")).toBeNull();
  });
});

describe("addExpansion", () => {
  it("asks again for the same node: each ask adds the next neighbours", () => {
    expect(addExpansion([], "N12", "callers")).toEqual(["N12:callers"]);
    expect(addExpansion(["N12:callers"], "N12", "callers")).toEqual(["N12:callers", "N12:callers"]);
    expect(addExpansion(["N12:callers"], "N9", "callees")).toEqual(["N12:callers", "N9:callees"]);
  });
});
