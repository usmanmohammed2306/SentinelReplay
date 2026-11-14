"use client";
import { useState } from "react";
import Editor, { loader } from "@monaco-editor/react";
import type { Comparison } from "@/lib/types";
loader.config({ paths: { vs: "/monaco/vs" } });

export default function PolicySource({
  comparison,
}: {
  comparison: Comparison;
}) {
  const [arm, setArm] = useState(comparison.branches[0].arm);
  const [language, setLanguage] = useState("json");
  const source = comparison.branches.find((item) => item.arm === arm)!;
  return (
    <section aria-label="Verified policy source">
      <h3>The policy behind the decision</h3>
      <p className="muted">
        Read the exact policy and compiled Rego bound to the executed branch.
        Editing or running a new candidate requires a separate evaluation.
      </p>
      <label>
        Executed policy{" "}
        <select
          aria-label="Policy source candidate"
          value={arm}
          onChange={(event) => setArm(event.target.value)}
        >
          {comparison.scores.map((row) => (
            <option key={row.arm} value={row.arm}>
              {row.arm.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </label>{" "}
      <label>
        Format{" "}
        <select
          aria-label="Policy source format"
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
        >
          <option value="json">Policy JSON</option>
          <option value="plaintext">Compiled Rego</option>
        </select>
      </label>
      <Editor
        height="340px"
        theme="vs-dark"
        language={language}
        value={
          language === "json"
            ? JSON.stringify(source.policy, null, 2)
            : source.rego
        }
        options={{
          readOnly: true,
          domReadOnly: true,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          fontSize: 13,
        }}
        loading={<p role="status">Loading local policy inspector…</p>}
      />
      <code>{source.policy_digest}</code>
    </section>
  );
}
