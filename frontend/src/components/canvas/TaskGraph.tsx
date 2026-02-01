
import { useMemo } from 'react'
import MermaidDiagram from '@/components/MermaidDiagram'

interface TaskNode {
    id: string
    title: string
    status: 'pending' | 'ready' | 'running' | 'completed' | 'failed' | 'skipped' | 'blocked'
    agent_type: string
}

interface TaskGraphData {
    nodes: Record<string, TaskNode>
    edges: Array<{ from: string; to: string }>
}

interface TaskGraphProps {
    data: string | TaskGraphData
    className?: string
}

export default function TaskGraph({ data, className }: TaskGraphProps) {
    const chart = useMemo(() => {
        try {
            const graph: TaskGraphData = typeof data === 'string' ? JSON.parse(data) : data

            if (!graph.nodes || Object.keys(graph.nodes).length === 0) {
                return 'graph TD\n  Start((Start))'
            }

            let mermaid = 'graph TD\n'

            // Define styles
            mermaid += '  %% Styles\n'
            mermaid += '  classDef default fill:#1e293b,stroke:#334155,color:#e2e8f0,stroke-width:2px\n'
            mermaid += '  classDef running fill:#3b82f6,stroke:#60a5fa,color:#fff,stroke-width:2px,stroke-dasharray: 5 5\n'
            mermaid += '  classDef completed fill:#059669,stroke:#34d399,color:#fff,stroke-width:2px\n'
            mermaid += '  classDef failed fill:#dc2626,stroke:#f87171,color:#fff,stroke-width:2px\n'
            mermaid += '  classDef ready fill:#475569,stroke:#94a3b8,color:#e2e8f0,stroke-width:2px\n'
            mermaid += '  classDef blocked fill:#1e293b,stroke:#dc2626,color:#94a3b8,stroke-width:2px,stroke-dasharray: 2 2\n'

            // Nodes
            Object.entries(graph.nodes).forEach(([id, node]) => {
                // Sanitize label
                const label = node.title.replace(/["\n]/g, '')
                const safeId = id.replace(/-/g, '_')

                // let shape = 'rect' // Unused
                // if (node.status === 'completed') shape = 'rounded'

                // Construct node string: id["Label"]
                // Using distinct brackets for shapes if desired, simplified for now
                mermaid += `  ${safeId}["<div style='font-weight:bold'>${label}</div><div style='font-size:0.8em'>${node.agent_type}</div>"]\n`

                // Assign class based on status
                let className = 'default'
                switch (node.status) {
                    case 'running': className = 'running'; break
                    case 'completed': className = 'completed'; break
                    case 'failed': className = 'failed'; break
                    case 'ready': className = 'ready'; break
                    case 'blocked': className = 'blocked'; break
                }
                mermaid += `  class ${safeId} ${className}\n`
            })

            // Edges
            if (graph.edges) {
                graph.edges.forEach(({ from, to }) => {
                    const safeFrom = from.replace(/-/g, '_')
                    const safeTo = to.replace(/-/g, '_')
                    mermaid += `  ${safeFrom} --> ${safeTo}\n`
                })
            }

            return mermaid
        } catch (e) {
            console.error('Failed to parse task graph data', e)
            return 'graph TD\n  Error["Failed to render graph"]\n  style Error fill:#dc2626,color:white'
        }
    }, [data])

    return (
        <div className={className}>
            <MermaidDiagram chart={chart} />
        </div>
    )
}
