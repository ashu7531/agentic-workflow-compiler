import { useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const TYPE_META = {
  fetch: { color: '#2563eb', bg: '#eff6ff', icon: '🔍', word: 'FETCH' },
  decision: { color: '#d97706', bg: '#fffbeb', icon: '◆', word: 'DECISION' },
  action: { color: '#059669', bg: '#ecfdf5', icon: '⚡', word: 'ACTION' },
};

// ── Custom node card (polished look) ──
function SopNode({ data }) {
  const meta = TYPE_META[data.type] || { color: '#64748b', bg: '#f1f5f9', icon: '•', word: data.type };
  const { status } = data;
  let ring = 'transparent';
  let opacity = 1;
  if (status === 'ran') ring = '#16a34a';
  if (status === 'error') ring = '#dc2626';
  if (status === 'skipped') opacity = 0.4;

  return (
    <div
      className="sop-node"
      style={{
        background: meta.bg,
        borderColor: meta.color,
        boxShadow: data.selected
          ? '0 0 0 3px #6366f1, 0 6px 16px rgba(0,0,0,0.12)'
          : status === 'ran'
          ? `0 0 0 2px ${ring}, 0 4px 12px rgba(0,0,0,0.08)`
          : '0 4px 12px rgba(0,0,0,0.06)',
        opacity,
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div className="sop-node__type" style={{ color: meta.color }}>
        <span>{meta.icon}</span> {meta.word}
      </div>
      <div className="sop-node__title">{data.label}</div>
      {data.tool && <div className="sop-node__meta">🔧 {data.tool}</div>}
      {data.condition && <div className="sop-node__cond">if {data.condition}</div>}
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { sop: SopNode };

function computeLevels(nodes, edges) {
  const ids = nodes.map((n) => n.id);
  const preds = Object.fromEntries(ids.map((id) => [id, []]));
  edges.forEach((e) => { if (preds[e.to]) preds[e.to].push(e.from); });
  const level = {};
  const visiting = {};
  function lvl(id) {
    if (level[id] !== undefined) return level[id];
    if (visiting[id]) return 0;
    visiting[id] = true;
    const ps = preds[id] || [];
    const v = ps.length === 0 ? 0 : Math.max(...ps.map(lvl)) + 1;
    level[id] = v;
    return v;
  }
  ids.forEach(lvl);
  return level;
}

function buildFlow(graph, runResult, selectedId) {
  const level = computeLevels(graph.nodes, graph.edges);
  const perLevel = {};
  const status = {};
  const chose = {};
  if (runResult?.trace) {
    runResult.trace.forEach((s) => {
      status[s.node] = s.status;
      if (s.type === 'decision' && s.chose) chose[s.node] = s.chose;
    });
  }

  const rfNodes = graph.nodes.map((n) => {
    const lv = level[n.id] || 0;
    const idx = perLevel[lv] || 0;
    perLevel[lv] = idx + 1;
    return {
      id: n.id,
      type: 'sop',
      position: { x: lv * 320 + 30, y: idx * 160 + 30 },
      data: {
        label: n.label || n.id,
        type: n.type,
        tool: n.tool,
        condition: n.condition,
        status: status[n.id],
        selected: selectedId === n.id,
      },
    };
  });

  const rfEdges = graph.edges.map((e, i) => {
    let taken = false;
    if (status[e.from] === 'ran' && status[e.to] === 'ran') {
      taken = e.branch == null || chose[e.from] === e.branch;
    }
    const color = e.branch === 'true' ? '#16a34a' : e.branch === 'false' ? '#ef4444' : '#94a3b8';
    const strokeColor = taken ? '#16a34a' : color;
    return {
      id: `e${i}`,
      source: e.from,
      target: e.to,
      label: e.branch === 'true' ? '✓ yes' : e.branch === 'false' ? '✗ no' : undefined,
      animated: taken,
      type: 'smoothstep',
      pathOptions: { borderRadius: 18 },
      markerEnd: { type: MarkerType.ArrowClosed, color: strokeColor, width: 18, height: 18 },
      style: {
        stroke: strokeColor,
        strokeWidth: taken ? 3 : 1.75,
        opacity: runResult && !taken ? 0.28 : 1,
      },
      labelStyle: { fontSize: 10, fill: color, fontWeight: 700 },
      labelBgStyle: { fill: '#fff', fillOpacity: 0.9 },
      labelBgPadding: [4, 2],
      labelBgBorderRadius: 4,
    };
  });

  return { rfNodes, rfEdges };
}

export default function GraphView({ graph, runResult, onSelectNode, selectedId }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Rebuild when the graph, run result, or selection changes — but PRESERVE
  // any positions the user has dragged.
  useEffect(() => {
    if (!graph) { setNodes([]); setEdges([]); return; }
    const { rfNodes, rfEdges } = buildFlow(graph, runResult, selectedId);
    setNodes((prev) =>
      rfNodes.map((n) => {
        const existing = prev.find((p) => p.id === n.id);
        return existing ? { ...n, position: existing.position } : n;
      })
    );
    setEdges(rfEdges);
  }, [graph, runResult, selectedId, setNodes, setEdges]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={(_, node) => onSelectNode?.(node.id)}
      onPaneClick={() => onSelectNode?.(null)}
      fitView
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#e2e8f0" gap={20} />
      <MiniMap pannable zoomable nodeStrokeWidth={2} />
      <Controls />
    </ReactFlow>
  );
}
