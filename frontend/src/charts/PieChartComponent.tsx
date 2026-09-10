import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

interface Props {
  data: Record<string, any>[];
  colors?: string[];
}

export default function PieChartComponent({ data, colors = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6'] }: Props) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label>
          {data.map((_, index) => (
            <Cell key={index} fill={colors[index % colors.length]} />
          ))}
        </Pie>
        <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 0 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}