import { useMemo } from 'react'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { cn } from '@/lib/utils'

// Color palette for charts
const COLORS = [
  '#8b5cf6', // violet
  '#06b6d4', // cyan
  '#f59e0b', // amber
  '#10b981', // emerald
  '#ec4899', // pink
  '#6366f1', // indigo
  '#f97316', // orange
  '#14b8a6', // teal
]

interface ChartData {
  [key: string]: string | number
}

interface ChartProps {
  type: 'line' | 'bar' | 'pie' | 'area'
  data: ChartData[]
  title?: string
  xKey?: string
  yKeys?: string[]
  className?: string
  height?: number
}

// Custom tooltip component
function CustomTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null

  return (
    <div className="bg-card border border-border rounded-lg p-3 shadow-lg">
      {label && <p className="text-sm font-medium text-foreground mb-1">{label}</p>}
      {payload.map((entry, index) => (
        <p key={index} className="text-sm" style={{ color: entry.color }}>
          {entry.name}: <span className="font-medium">{entry.value.toLocaleString()}</span>
        </p>
      ))}
    </div>
  )
}

export default function Chart({
  type,
  data,
  title,
  xKey = 'name',
  yKeys,
  className,
  height = 300,
}: ChartProps) {
  // Auto-detect y keys if not provided
  const detectedYKeys = useMemo(() => {
    if (yKeys?.length) return yKeys
    if (!data.length) return []
    const keys = Object.keys(data[0]).filter(
      (key) => key !== xKey && typeof data[0][key] === 'number'
    )
    return keys
  }, [data, xKey, yKeys])

  if (!data.length) {
    return (
      <div className={cn('chart-container', className)}>
        <p className="text-muted-foreground text-center py-8">No data available</p>
      </div>
    )
  }

  const chartContent = useMemo(() => {
    switch (type) {
      case 'line':
        return (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis
              dataKey={xKey}
              stroke="hsl(var(--muted-foreground))"
              fontSize={12}
              tickLine={false}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            {detectedYKeys.map((key, index) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={COLORS[index % COLORS.length]}
                strokeWidth={2}
                dot={{ fill: COLORS[index % COLORS.length], strokeWidth: 0, r: 4 }}
                activeDot={{ r: 6, strokeWidth: 0 }}
              />
            ))}
          </LineChart>
        )

      case 'bar':
        return (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis
              dataKey={xKey}
              stroke="hsl(var(--muted-foreground))"
              fontSize={12}
              tickLine={false}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            {detectedYKeys.map((key, index) => (
              <Bar
                key={key}
                dataKey={key}
                fill={COLORS[index % COLORS.length]}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        )

      case 'area':
        return (
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis
              dataKey={xKey}
              stroke="hsl(var(--muted-foreground))"
              fontSize={12}
              tickLine={false}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            {detectedYKeys.map((key, index) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stroke={COLORS[index % COLORS.length]}
                fill={COLORS[index % COLORS.length]}
                fillOpacity={0.2}
                strokeWidth={2}
              />
            ))}
          </AreaChart>
        )

      case 'pie':
        // For pie charts, use the first y key or "value"
        const pieKey = detectedYKeys[0] || 'value'
        return (
          <PieChart>
            <Pie
              data={data}
              dataKey={pieKey}
              nameKey={xKey}
              cx="50%"
              cy="50%"
              outerRadius={80}
              label={({ name, percent }) => `${name} (${((percent ?? 0) * 100).toFixed(0)}%)`}
              labelLine={{ stroke: 'hsl(var(--muted-foreground))' }}
            >
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
            <Legend />
          </PieChart>
        )

      default:
        return null
    }
  }, [type, data, xKey, detectedYKeys])

  return (
    <div className={cn('chart-container my-4', className)}>
      {title && (
        <h4 className="text-sm font-medium text-foreground mb-4">{title}</h4>
      )}
      <ResponsiveContainer width="100%" height={height}>
        {chartContent}
      </ResponsiveContainer>
    </div>
  )
}

// Helper to parse chart data from code blocks
export function parseChartData(content: string): { type: ChartProps['type']; data: ChartData[]; title?: string } | null {
  try {
    const parsed = JSON.parse(content)
    if (parsed.type && parsed.data && Array.isArray(parsed.data)) {
      return {
        type: parsed.type,
        data: parsed.data,
        title: parsed.title,
      }
    }
    // If it's just an array, default to bar chart
    if (Array.isArray(parsed)) {
      return { type: 'bar', data: parsed }
    }
  } catch {
    // Not valid JSON
  }
  return null
}

// Helper to detect chart code blocks
export function isChartCode(language: string): boolean {
  return language.toLowerCase() === 'chart' || language.toLowerCase() === 'chart-json'
}
