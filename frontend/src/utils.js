
export const formatValue = (val, base, width = 8) => {
  const num = parseInt(val) || 0;
  if (base === "bin") return num.toString(2).padStart(width, "0");
  if (base === "hex") return "0x" + num.toString(16).toUpperCase();
  return num.toString(10);
};

export function nextFreeIndex(nodes, type) {
  const used = nodes
    .filter((n) => n.type === type)
    .map((n) => {
      const parts = n.id.split("_");
      return Number(parts[parts.length - 1]);
    })
    .filter((n) => !isNaN(n))
    .sort((a, b) => a - b);
  let i = 0;
  while (used.includes(i)) {
    i++;
  }
  return i;
}

export const detectLoops = (nodes, edges) => {
  const loops = [];
  const visited = new Set();
  const recStack = new Set();

  const dfs = (nodeId, path) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return false;

    if (
      node.type === "reg" ||
      node.type === "fsm_state" ||
      node.type.startsWith("macro_")
    ) {
      return false;
    }

    visited.add(nodeId);
    recStack.add(nodeId);

    const outgoingEdges = edges.filter((e) => e.source === nodeId);

    for (let edge of outgoingEdges) {
      const neighborId = edge.target;
      if (recStack.has(neighborId)) {
        const startIndex = path.indexOf(neighborId);
        const circularPath =
          startIndex !== -1 ? path.slice(startIndex) : path;
        loops.push(
          `Infinite Loop: ${circularPath.join(" -> ")} -> ${neighborId}`
        );
        return true;
      }
      if (!visited.has(neighborId)) {
        const neighborNode = nodes.find((n) => n.id === neighborId);
        const nextPathName = neighborNode?.data?.name || neighborId;
        if (dfs(neighborId, [...path, nextPathName])) return true;
      }
    }

    recStack.delete(nodeId);
    return false;
  };

  nodes.forEach((node) => {
    if (!visited.has(node.id)) {
      dfs(node.id, [node.data.name || node.id]);
    }
  });

  return loops;
};

export const stripNodeForSave = (n) => {
  const {
    onDelete,
    setWidth,
    setBitIndex,
    setMuxSize,
    setJoinerSize,
    setValue,
    setIterations,
    setFifoDepth,
    setAeThresh,
    rename,
    setLsbPriority,
    setFsmOutputs,
    setEdgeType,
    setAddrWidth,
    setCountDir,
    onChangeValue,
    isMacro,
    ...cleanData
  } = n.data;
  return { ...n, data: cleanData };
};
