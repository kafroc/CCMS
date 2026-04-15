<template>
  <div class="chain-tree" ref="containerRef">
    <svg :width="svgWidth" :height="svgHeight" class="chain-tree-svg">
      <!-- Cross-layer dashed edges -->
      <line
        v-for="(edge, idx) in renderedEdges"
        :key="'e-' + idx"
        :x1="edge.x1" :y1="edge.y1"
        :x2="edge.x2" :y2="edge.y2"
        :stroke="edge.highlighted ? '#18a058' : '#d0d0d0'"
        :stroke-width="edge.highlighted ? 2 : 1"
        stroke-dasharray="6 4"
        :opacity="hasSelection && !edge.highlighted ? 0.15 : 1"
        class="chain-edge"
      />
      <!-- SFR dependency arcs -->
      <path
        v-for="(arc, idx) in renderedSfrArcs"
        :key="'arc-' + idx"
        :d="arc.d"
        fill="none"
        :stroke="arc.highlighted ? '#18a058' : '#c0c0c0'"
        :stroke-width="arc.highlighted ? 2 : 1"
        stroke-dasharray="4 3"
        :opacity="hasSelection && !arc.highlighted ? 0.15 : 1"
      />
    </svg>
    <!-- Layers -->
    <div
      v-for="(layer, layerIdx) in renderedLayers"
      :key="layer.key"
      class="chain-layer"
    >
      <div class="layer-label">{{ layerLabels[layer.key] || layer.key }}</div>
      <div class="layer-nodes" :ref="el => setLayerRef(layerIdx, el as HTMLElement)">
        <div
          v-for="node in layer.nodes"
          :key="node.id"
          :ref="el => setNodeRef(node.id, el as HTMLElement)"
          class="tree-node"
          :class="[
            'node-' + node.type,
            {
              'node-selected': selectedNodeId === node.id,
              'node-highlighted': highlightedNodeIds.has(node.id),
              'node-dimmed': hasSelection && !highlightedNodeIds.has(node.id) && selectedNodeId !== node.id,
            },
          ]"
          @click="toggleNode(node.id)"
        >
          <span class="node-icon">{{ nodeIcon(node) }}</span>
          <span class="node-label">{{ node.label }}</span>
          <span v-if="node.type === 'threat' && node.risk_level" class="node-badge" :class="'badge-' + node.risk_level">
            {{ node.risk_level }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import type { ChainTreeData, ChainTreeNode, ChainTreeEdge } from '@/api/risk'

const props = defineProps<{
  data: ChainTreeData
  labels: Record<string, string>
}>()

const containerRef = ref<HTMLElement | null>(null)
const nodeRefs = ref<Record<string, HTMLElement>>({})
const layerRefs = ref<HTMLElement[]>([])
const selectedNodeId = ref<string | null>(null)
const svgWidth = ref(1200)
const svgHeight = ref(600)



function setNodeRef(id: string, el: HTMLElement | null) {
  if (el) nodeRefs.value[id] = el
}
function setLayerRef(idx: number, el: HTMLElement | null) {
  if (el) layerRefs.value[idx] = el
}

const layerLabels = computed(() => props.labels)

const renderedLayers = computed(() => props.data?.layers ?? [])



// Build adjacency maps for highlight traversal
const adjacencyDown = computed(() => {
  const map: Record<string, Set<string>> = {}
  for (const edge of (props.data?.edges ?? [])) {
    if (!map[edge.from]) map[edge.from] = new Set()
    map[edge.from].add(edge.to)
  }
  return map
})

const adjacencyUp = computed(() => {
  const map: Record<string, Set<string>> = {}
  for (const edge of (props.data?.edges ?? [])) {
    if (!map[edge.to]) map[edge.to] = new Set()
    map[edge.to].add(edge.from)
  }
  return map
})

// All node ids by layer index for quick lookup
const nodeLayerIndex = computed(() => {
  const map: Record<string, number> = {}
  renderedLayers.value.forEach((layer, idx) => {
    for (const node of layer.nodes) {
      map[node.id] = idx
    }
  })
  return map
})

const hasSelection = computed(() => selectedNodeId.value !== null)

// Highlight: traverse downward first, then upward from ALL reached nodes
const highlightedNodeIds = computed(() => {
  const set = new Set<string>()
  if (!selectedNodeId.value) return set
  set.add(selectedNodeId.value)
  // traverse downward
  const queue = [selectedNodeId.value]
  while (queue.length > 0) {
    const current = queue.shift()!
    for (const child of (adjacencyDown.value[current] ?? [])) {
      if (!set.has(child)) { set.add(child); queue.push(child) }
    }
  }
  // traverse upward from the clicked node only
  const queue2 = [selectedNodeId.value]
  const visited = new Set<string>([selectedNodeId.value])
  while (queue2.length > 0) {
    const current = queue2.shift()!
    for (const parent of (adjacencyUp.value[current] ?? [])) {
      if (!visited.has(parent)) { visited.add(parent); set.add(parent); queue2.push(parent) }
    }
  }
  return set
})

const highlightedEdgeSet = computed(() => {
  const set = new Set<string>()
  if (!selectedNodeId.value) return set
  for (const edge of (props.data?.edges ?? [])) {
    if (highlightedNodeIds.value.has(edge.from) && highlightedNodeIds.value.has(edge.to)) {
      set.add(edge.from + '->' + edge.to)
    }
  }
  return set
})

// Compute edge line positions based on actual DOM positions
const edgePositions = ref<Array<{ x1: number; y1: number; x2: number; y2: number; from: string; to: string }>>([])
const sfrArcPositions = ref<Array<{ d: string; from: string; to: string }>>([])

function recalcEdges() {
  if (!containerRef.value) return
  const containerRect = containerRef.value.getBoundingClientRect()
  const positions: typeof edgePositions.value = []
  const arcs: typeof sfrArcPositions.value = []
  for (const edge of (props.data?.edges ?? [])) {
    const fromEl = nodeRefs.value[edge.from]
    const toEl = nodeRefs.value[edge.to]
    if (!fromEl || !toEl) continue
    const fromRect = fromEl.getBoundingClientRect()
    const toRect = toEl.getBoundingClientRect()
    if (edge.type === 'sfr_dependency') {
      // Curved arc below the SFR nodes
      const x1 = fromRect.left + fromRect.width / 2 - containerRect.left
      const y1 = fromRect.top + fromRect.height - containerRect.top
      const x2 = toRect.left + toRect.width / 2 - containerRect.left
      const y2 = toRect.top + toRect.height - containerRect.top
      const midX = (x1 + x2) / 2
      const dist = Math.abs(x2 - x1)
      const curveY = Math.max(y1, y2) + Math.min(dist * 0.3, 40) + 10
      arcs.push({
        d: `M ${x1} ${y1} Q ${midX} ${curveY} ${x2} ${y2}`,
        from: edge.from,
        to: edge.to,
      })
    } else {
      positions.push({
        x1: fromRect.left + fromRect.width / 2 - containerRect.left,
        y1: fromRect.top + fromRect.height - containerRect.top,
        x2: toRect.left + toRect.width / 2 - containerRect.left,
        y2: toRect.top - containerRect.top,
        from: edge.from,
        to: edge.to,
      })
    }
  }
  edgePositions.value = positions
  sfrArcPositions.value = arcs
  // Update svg dimensions
  svgWidth.value = containerRef.value.scrollWidth
  svgHeight.value = containerRef.value.scrollHeight
}

const renderedEdges = computed(() => {
  return edgePositions.value.map(ep => ({
    ...ep,
    highlighted: highlightedEdgeSet.value.has(ep.from + '->' + ep.to),
  }))
})

const renderedSfrArcs = computed(() => {
  return sfrArcPositions.value.map(arc => ({
    ...arc,
    highlighted: highlightedEdgeSet.value.has(arc.from + '->' + arc.to),
  }))
})

function toggleNode(nodeId: string) {
  selectedNodeId.value = selectedNodeId.value === nodeId ? null : nodeId
}

function nodeIcon(node: ChainTreeNode): string {
  switch (node.type) {
    case 'asset': return '📦'
    case 'threat': return '⚠️'
    case 'assumption': return '💭'
    case 'osp': return '📋'
    case 'objective': return '🎯'
    case 'sfr': return '🔒'
    case 'test': return '🧪'
    default: return '●'
  }
}

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  nextTick(() => { recalcEdges() })
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => { recalcEdges() })
    resizeObserver.observe(containerRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})

watch(() => props.data, () => {
  nodeRefs.value = {}
  layerRefs.value = []
  nextTick(() => { setTimeout(recalcEdges, 50) })
}, { deep: true })
</script>

<style scoped>
.chain-tree {
  position: relative;
  padding: 0 8px 16px;
  overflow-x: auto;
}
.chain-tree-svg {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  z-index: 0;
}
.chain-layer {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  z-index: 1;
  margin-bottom: 48px;
}
.layer-label {
  flex-shrink: 0;
  width: 100px;
  text-align: right;
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding-top: 8px;
}
.layer-nodes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  flex: 1;
}
.tree-node {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1.5px solid #e4e7ed;
  background: #fff;
  font-size: 12px;
  color: #303133;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  user-select: none;
  position: relative;
}
.tree-node:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
}
.node-selected {
  border-color: #18a058 !important;
  background: #f0faf4 !important;
  box-shadow: 0 0 0 2px rgba(24, 160, 88, 0.2) !important;
}
.node-highlighted {
  border-color: #18a058;
  background: #f6ffed;
}
.node-dimmed {
  opacity: 0.2;
}
.node-icon {
  font-size: 14px;
}
.node-label {
  font-weight: 500;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.node-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
  text-transform: uppercase;
  color: #fff;
}
.badge-critical { background: #8B0000; }
.badge-high { background: #d03050; }
.badge-medium { background: #f0a020; }
.badge-low { background: #18a058; }

.node-asset { border-color: #b3d8ff; background: #f0f9ff; }
.node-threat { border-color: #fcd5ce; background: #fff5f0; }
.node-assumption { border-color: #d9ecff; background: #f5f7fa; }
.node-osp { border-color: #d9ecff; background: #f5f7fa; }
.node-objective { border-color: #fde2c8; background: #fff8f0; }
.node-sfr { border-color: #c8e6c9; background: #f0faf4; }
.node-test { border-color: #d1c4e9; background: #f3f0ff; }
</style>
