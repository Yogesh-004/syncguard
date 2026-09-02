import os

# Fix Records.tsx
with open('pages/Records.tsx') as f:
    content = f.read()
content = content.replace("import React, { useState } from 'react';\n", "import { useState } from 'react';\n")
content = content.replace('const { data, isLoading } = useQuery', 'const { isLoading } = useQuery')
with open('pages/Records.tsx', 'w') as f:
    f.write(content)

# Fix all pages with unused React import
files = ['pages/Dashboard.tsx', 'pages/Conflicts.tsx', 'pages/Jobs.tsx', 'pages/Matching.tsx', 'pages/Sources.tsx', 'App.tsx']
for f in files:
    with open(f) as fh:
        content = fh.read()
    content = content.replace("import React from 'react';\n", '')
    with open(f, 'w') as fh:
        fh.write(content)

# Fix BarChartComponent.tsx
with open('charts/BarChartComponent.tsx') as fh:
    content = fh.read()
content = content.replace("import React from 'react';\n", '')
content = content.replace('  name?: string;\n', '')
content = content.replace(', name = "Value"', '')
with open('charts/BarChartComponent.tsx', 'w') as fh:
    fh.write(content)

# Fix LineChartComponent.tsx
with open('charts/LineChartComponent.tsx') as fh:
    content = fh.read()
content = content.replace("import React from 'react';\n", '')
content = content.replace('  name?: string;\n', '')
content = content.replace(', name = "Value"', '')
with open('charts/LineChartComponent.tsx', 'w') as fh:
    fh.write(content)

# Fix PieChartComponent.tsx
with open('charts/PieChartComponent.tsx') as fh:
    content = fh.read()
content = content.replace("import React from 'react';\n", '')
content = content.replace('data.map((entry, index) => (', 'data.map((_, index) => (')
with open('charts/PieChartComponent.tsx', 'w') as fh:
    fh.write(content)

print('Done')