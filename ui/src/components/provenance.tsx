"use client";
import { Background, Controls, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Graph } from "@/lib/types";

export default function Provenance({
  graph,
  onSelect,
}: {
  graph: Graph;
  onSelect: (step: number) => void;
}) {
  return (
    <div className="graph-canvas" aria-label="Declared dependency graph">
      <ReactFlow
        colorMode="dark"
        fitView
        nodes={graph.nodes.map((node, i) => ({
          id: String(node.step),
          position: { x: (i % 3) * 260, y: Math.floor(i / 3) * 150 },
          data: {
            label: (
              <>
                <small>STEP {node.step}</small>
                <br />
                {node.operation.replaceAll("_", " ")}
              </>
            ),
          },
          style: {
            background: node.step === graph.root_step ? "#293e39" : "#172024",
            color: "#e4e8e3",
            borderColor: node.step === graph.root_step ? "#70bba4" : "#344249",
            width: 220,
            borderRadius: 8,
          },
        }))}
        edges={graph.edges.map((edge, i) => ({
          id: String(i),
          source: String(edge.source),
          target: String(edge.target),
          label: edge.kind.replace("declared_", ""),
          style: { stroke: "#71bca5" },
          labelStyle: { fill: "#ccd5d0" },
        }))}
        onNodeClick={(_, node) => onSelect(Number(node.id))}
        nodesDraggable={false}
        minZoom={0.25}
        maxZoom={1.5}
      >
        <Background color="#334047" gap={24} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
