import { execSync } from "node:child_process";
import { describe, expect, it } from "vitest";

interface DependencyNode {
  version?: string;
  dependencies?: Record<string, DependencyNode>;
}

function collectOnnxRuntimeVersions(node: DependencyNode, versions: Set<string>): void {
  for (const [name, dependency] of Object.entries(node.dependencies ?? {})) {
    if (name === "onnxruntime-web" && dependency.version) versions.add(dependency.version);
    collectOnnxRuntimeVersions(dependency, versions);
  }
}

describe("Kokoro runtime compatibility", () => {
  it("installs one ONNX Runtime Web version for model sessions and tensors", () => {
    const output = execSync("pnpm list onnxruntime-web --json --depth Infinity", {
      cwd: process.cwd(),
      encoding: "utf8",
    });
    const projects = JSON.parse(output) as DependencyNode[];
    const versions = new Set<string>();
    for (const project of projects) collectOnnxRuntimeVersions(project, versions);

    expect([...versions]).toEqual(["1.22.0-dev.20250409-89f8206ba4"]);
  });
});
