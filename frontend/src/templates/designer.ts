export interface TemplateField {
  key: string
  label: string
  symbol: string
  type: 'number' | 'integer' | 'text'
  unit: string
  precision: number
  required: boolean
  min?: number
  max?: number
}

export interface TemplateTable {
  id: string
  title: string
  description: string
  minimumRows: number
  maximumRows: number
  fields: TemplateField[]
  grid?: SpreadsheetGrid
}

export interface SpreadsheetCell {
  id: string
  row: number
  column: number
  rowSpan: number
  colSpan: number
  kind: 'label' | 'field'
  text: string
  fieldKey?: string
}

export interface SpreadsheetGrid {
  rows: number
  columns: number
  cells: SpreadsheetCell[]
}

export interface CellRange {
  startRow: number
  endRow: number
  startColumn: number
  endColumn: number
}

export interface OperationStep {
  id: string
  title: string
  instruction: string
  tableId?: string
}

export interface TemplateCalculation {
  key: string
  label: string
  function: 'MEAN' | 'STD' | 'ABS' | 'SQRT' | 'POW' | 'LINEAR_SLOPE' | 'LINEAR_INTERCEPT' | 'R_SQUARED'
  args: string[]
  unit: string
  parameters?: number[]
}

export interface TemplateChart {
  title: string
  type: 'scatter' | 'line'
  x: string
  y: string
  fit?: 'linear'
}

export interface TemplateSchema {
  title: string
  description: string
  objectives: string[]
  preparationQuestions: string[]
  discussionQuestions: string[]
  steps: OperationStep[]
  tables: TemplateTable[]
  calculations: TemplateCalculation[]
  charts: TemplateChart[]
  checks: Array<Record<string, unknown>>
  requiredArtifacts: string[]
}

const numberField = (
  key: string,
  label: string,
  symbol: string,
  unit: string,
  precision: number,
  min?: number,
  max?: number,
): TemplateField => ({ key, label, symbol, type: 'number', unit, precision, required: true, min, max })

const cellId = (row: number, column: number) => `r${row + 1}c${column + 1}`

function defaultCell(row: number, column: number, fields: TemplateField[]): SpreadsheetCell {
  const field = fields[column]
  if (row === 0) {
    return { id: cellId(row, column), row, column, rowSpan: 1, colSpan: 1, kind: 'label', text: field?.label || `第 ${column + 1} 列` }
  }
  return {
    id: cellId(row, column), row, column, rowSpan: 1, colSpan: 1,
    kind: field ? 'field' : 'label', text: '', fieldKey: field?.key,
  }
}

export function createSpreadsheetGrid(fields: TemplateField[], dataRows: number): SpreadsheetGrid {
  const columns = Math.max(1, fields.length)
  const rows = Math.max(2, Math.min(201, dataRows + 1))
  return {
    rows,
    columns,
    cells: Array.from({ length: rows }, (_, row) =>
      Array.from({ length: columns }, (_, column) => defaultCell(row, column, fields)),
    ).flat(),
  }
}

function covers(cell: SpreadsheetCell, row: number, column: number) {
  return row >= cell.row && row < cell.row + cell.rowSpan && column >= cell.column && column < cell.column + cell.colSpan
}

export function cellAt(grid: SpreadsheetGrid, row: number, column: number) {
  return grid.cells.find((cell) => covers(cell, row, column))
}

export function normalizeSpreadsheetGrid(raw: SpreadsheetGrid | undefined, fields: TemplateField[], dataRows: number): SpreadsheetGrid {
  if (!raw || !Number.isInteger(raw.rows) || !Number.isInteger(raw.columns) || !Array.isArray(raw.cells)) {
    return createSpreadsheetGrid(fields, dataRows)
  }
  const rows = Math.max(2, Math.min(201, raw.rows))
  const columns = Math.max(1, Math.min(30, raw.columns))
  const cells = raw.cells
    .filter((cell) => cell.row >= 0 && cell.column >= 0 && cell.row < rows && cell.column < columns)
    .map((cell) => ({
      ...cell,
      rowSpan: Math.max(1, Math.min(cell.rowSpan || 1, rows - cell.row)),
      colSpan: Math.max(1, Math.min(cell.colSpan || 1, columns - cell.column)),
    }))
  const grid: SpreadsheetGrid = { rows, columns, cells: [] }
  for (const cell of cells.sort((a, b) => a.row - b.row || a.column - b.column)) {
    const overlaps = grid.cells.some((existing) => {
      for (let row = cell.row; row < cell.row + cell.rowSpan; row += 1) {
        for (let column = cell.column; column < cell.column + cell.colSpan; column += 1) {
          if (covers(existing, row, column)) return true
        }
      }
      return false
    })
    if (!overlaps) grid.cells.push(cell)
  }
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      if (!cellAt(grid, row, column)) grid.cells.push(defaultCell(row, column, fields))
    }
  }
  return grid
}

export function resizeSpreadsheetGrid(grid: SpreadsheetGrid, rows: number, columns: number, fields: TemplateField[]) {
  return normalizeSpreadsheetGrid({ ...grid, rows, columns }, fields, rows - 1)
}

export function mergeSpreadsheetCells(grid: SpreadsheetGrid, range: CellRange): SpreadsheetGrid {
  const startRow = Math.min(range.startRow, range.endRow)
  const endRow = Math.max(range.startRow, range.endRow)
  const startColumn = Math.min(range.startColumn, range.endColumn)
  const endColumn = Math.max(range.startColumn, range.endColumn)
  const selected = grid.cells.filter((cell) => {
    const overlaps = cell.row <= endRow && cell.row + cell.rowSpan - 1 >= startRow && cell.column <= endColumn && cell.column + cell.colSpan - 1 >= startColumn
    if (!overlaps) return false
    if (cell.row < startRow || cell.column < startColumn || cell.row + cell.rowSpan - 1 > endRow || cell.column + cell.colSpan - 1 > endColumn) {
      throw new Error('选区边界穿过了已合并单元格，请先拆分后再合并。')
    }
    return true
  })
  if ((endRow - startRow + 1) * (endColumn - startColumn + 1) < 2) throw new Error('请至少选择两个单元格。')
  if (selected.some((cell) => cell.kind === 'field')) throw new Error('数据输入单元格不能合并，请只合并标题或说明单元格。')
  const anchor = cellAt(grid, startRow, startColumn)
  if (!anchor) throw new Error('选区无效。')
  const selectedIds = new Set(selected.map((cell) => cell.id))
  return {
    ...grid,
    cells: [
      ...grid.cells.filter((cell) => !selectedIds.has(cell.id)),
      { ...anchor, id: cellId(startRow, startColumn), row: startRow, column: startColumn, rowSpan: endRow - startRow + 1, colSpan: endColumn - startColumn + 1 },
    ].sort((a, b) => a.row - b.row || a.column - b.column),
  }
}

export function splitSpreadsheetCell(grid: SpreadsheetGrid, row: number, column: number, fields: TemplateField[]): SpreadsheetGrid {
  const target = cellAt(grid, row, column)
  if (!target || (target.rowSpan === 1 && target.colSpan === 1)) return grid
  const additions: SpreadsheetCell[] = []
  for (let currentRow = target.row; currentRow < target.row + target.rowSpan; currentRow += 1) {
    for (let currentColumn = target.column; currentColumn < target.column + target.colSpan; currentColumn += 1) {
      additions.push(currentRow === target.row && currentColumn === target.column
        ? { ...target, rowSpan: 1, colSpan: 1 }
        : defaultCell(currentRow, currentColumn, fields))
    }
  }
  return { ...grid, cells: [...grid.cells.filter((cell) => cell.id !== target.id), ...additions].sort((a, b) => a.row - b.row || a.column - b.column) }
}

export function ensureTableGrid(table: TemplateTable) {
  table.grid = normalizeSpreadsheetGrid(table.grid, table.fields, table.minimumRows)
  return table
}

export function createBlankTemplate(): TemplateSchema {
  return {
    title: '新实验模板',
    description: '',
    objectives: [],
    preparationQuestions: [],
    discussionQuestions: [],
    steps: [{ id: 'step_1', title: '实验步骤 1', instruction: '说明学生需要完成的操作。' }],
    tables: [{
      id: 'table_1',
      title: '数据记录表 1',
      description: '',
      minimumRows: 1,
      maximumRows: 10,
      fields: [numberField('value_1', '测量值', 'x', '1', 2)],
    }],
    calculations: [],
    charts: [],
    checks: [{ type: 'minimum_rows', tableId: 'table_1', value: 1 }],
    requiredArtifacts: ['data_image', 'excel'],
  }
}

export function createMechanicsTemplate(): TemplateSchema {
  return {
    title: '力学综合实验',
    description: '研究气垫导轨滑块的简谐振动、周期与振幅和质量的关系，以及弱阻尼下速度峰值的变化。',
    objectives: [
      '测量不同振幅下滑块的振动周期',
      '测量不同质量下滑块的振动周期并求弹簧劲度系数',
      '比较光电门与 PASCO 数据，研究弱阻尼下速度峰值的衰减',
    ],
    preparationQuestions: [
      '列举三种以上近似简谐振动现象，并说明其中一种与理想模型的差异。',
      '分析滑块在气垫导轨上振动时的受力，并画出受力图。',
      '推导无阻尼和速度正比阻尼条件下滑块的动力学方程。',
      '说明振动周期、速度、位移和相位之间的关系。',
      '说明光电门测量周期和速度的机理，以及两种挡光片的作用。',
    ],
    discussionQuestions: [
      '列举四种以上会损伤气垫导轨的实验行为或情况。',
      '分析弹簧质量对滑块振动的影响，并尝试由测量数据求出弹簧质量。',
      '讨论气垫导轨未调水平时运动是否仍为简谐振动、周期是否改变，并比较竖直弹簧情形。',
      '提出描述速度峰值随时间衰减的定量关系，并说明需要进行的数据处理和参数提取。',
      '总结实验中的系统误差和随机误差，并提出改进方法。',
    ],
    steps: [
      { id: 'level_track', title: '调平并检查装置', instruction: '检查气垫导轨、滑块、弹簧和光电门，确认导轨水平且滑块运动顺畅。' },
      { id: 'amplitude_period', title: '改变振幅测周期', instruction: '保持滑块质量不变，分别在 10 cm、15 cm、20 cm 振幅下重复测量周期。', tableId: 'amplitude_periods' },
      { id: 'mass_period', title: '改变质量测周期', instruction: '保持振幅 20 cm，依次改变砝码质量并重复测量周期。', tableId: 'mass_periods' },
      { id: 'damped_speed', title: '记录弱阻尼速度', instruction: '在平衡位置用光电门连续记录速度，并与 PASCO 数据中的平衡位置时刻对应。', tableId: 'damped_speeds' },
      { id: 'peak_decay', title: '提取速度峰值', instruction: '从 PASCO 数据提取平衡位置时刻和速度峰值，记录时间—速度数据用于衰减分析。', tableId: 'peak_decay' },
    ],
    tables: [
      {
        id: 'amplitude_periods',
        title: '不同振幅下的振子周期',
        description: '滑块质量保持不变，每个振幅测量三次。',
        minimumRows: 3,
        maximumRows: 3,
        fields: [
          numberField('amplitude_cm', '振幅', 'A', 'cm', 1, 0),
          numberField('period_amp_1_s', '周期第 1 次', 'T₁', 's', 3, 0),
          numberField('period_amp_2_s', '周期第 2 次', 'T₂', 's', 3, 0),
          numberField('period_amp_3_s', '周期第 3 次', 'T₃', 's', 3, 0),
        ],
      },
      {
        id: 'mass_periods',
        title: '不同质量下的振子周期',
        description: '振幅保持 20 cm，记录砝码质量、传感器质量以及三次周期。',
        minimumRows: 5,
        maximumRows: 8,
        fields: [
          numberField('added_mass_g', '砝码质量', 'm', 'g', 1, 0),
          numberField('total_mass_g', '振子总质量', 'M', 'g', 1, 0),
          numberField('period_mass_1_s', '周期第 1 次', 'T₁', 's', 3, 0),
          numberField('period_mass_2_s', '周期第 2 次', 'T₂', 's', 3, 0),
          numberField('period_mass_3_s', '周期第 3 次', 'T₃', 's', 3, 0),
        ],
      },
      {
        id: 'damped_speeds',
        title: '弱阻尼下平衡位置速度',
        description: '振幅 20 cm、平衡位置 x=0 cm，连续记录 30 次经过平衡位置的速度。',
        minimumRows: 30,
        maximumRows: 30,
        fields: [
          numberField('speed_sequence', '序号', 'n', '1', 0, 1, 30),
          numberField('equilibrium_speed_m_s', '速度', 'v', 'm/s', 3),
        ],
      },
      {
        id: 'peak_decay',
        title: '平衡位置速度峰值变化',
        description: '将 PASCO 中的平衡位置时刻与对应速度峰值逐行记录。',
        minimumRows: 10,
        maximumRows: 30,
        fields: [
          numberField('peak_sequence', '序号', 'n', '1', 0, 1),
          numberField('peak_time_s', '时间', 't', 's', 3, 0),
          numberField('peak_speed_m_s', '速度峰值', 'vₘ', 'm/s', 3),
        ],
      },
    ],
    calculations: [
      { key: 'mean_period_amplitude_s', label: '不同振幅的平均周期', function: 'MEAN', args: ['period_amp_1_s', 'period_amp_2_s', 'period_amp_3_s'], unit: 's' },
      { key: 'mean_period_mass_s', label: '不同质量的平均周期', function: 'MEAN', args: ['period_mass_1_s', 'period_mass_2_s', 'period_mass_3_s'], unit: 's' },
      { key: 'period_squared_mass_s2', label: '平均周期平方', function: 'POW', args: ['mean_period_mass_s'], unit: 's²', parameters: [2] },
    ],
    charts: [
      { title: '周期与振幅关系', type: 'scatter', x: 'amplitude_cm', y: 'mean_period_amplitude_s' },
      { title: '周期平方与振子质量关系', type: 'scatter', x: 'total_mass_g', y: 'period_squared_mass_s2', fit: 'linear' },
      { title: '速度峰值随时间变化', type: 'scatter', x: 'peak_time_s', y: 'peak_speed_m_s' },
    ],
    checks: [
      { type: 'minimum_rows', tableId: 'amplitude_periods', value: 3 },
      { type: 'minimum_rows', tableId: 'mass_periods', value: 5 },
      { type: 'minimum_rows', tableId: 'damped_speeds', value: 30 },
      { type: 'minimum_rows', tableId: 'peak_decay', value: 10 },
    ],
    requiredArtifacts: ['data_image', 'charts', 'excel', 'conclusion'],
  }
}

export function normalizeTemplateSchema(raw: Record<string, unknown>, fallbackName: string, fallbackDescription: string): TemplateSchema {
  const blank = createBlankTemplate()
  const tables = Array.isArray(raw.tables) ? raw.tables as TemplateTable[] : blank.tables
  return {
    title: typeof raw.title === 'string' ? raw.title : fallbackName,
    description: typeof raw.description === 'string' ? raw.description : fallbackDescription,
    objectives: Array.isArray(raw.objectives) ? raw.objectives.filter((item): item is string => typeof item === 'string') : [],
    preparationQuestions: Array.isArray(raw.preparationQuestions) ? raw.preparationQuestions.filter((item): item is string => typeof item === 'string') : [],
    discussionQuestions: Array.isArray(raw.discussionQuestions) ? raw.discussionQuestions.filter((item): item is string => typeof item === 'string') : [],
    steps: Array.isArray(raw.steps) ? raw.steps as OperationStep[] : [],
    tables: tables.map((table) => ensureTableGrid(table)),
    calculations: Array.isArray(raw.calculations) ? raw.calculations as TemplateCalculation[] : [],
    charts: Array.isArray(raw.charts) ? raw.charts as TemplateChart[] : [],
    checks: Array.isArray(raw.checks) ? raw.checks as Array<Record<string, unknown>> : [],
    requiredArtifacts: Array.isArray(raw.requiredArtifacts) ? raw.requiredArtifacts.filter((item): item is string => typeof item === 'string') : [],
  }
}

export function schemaValueOptions(schema: TemplateSchema) {
  return [
    ...schema.tables.flatMap((table) => table.fields.map((field) => ({ key: field.key, label: `${table.title} · ${field.label}` }))),
    ...schema.calculations.map((calculation) => ({ key: calculation.key, label: `计算结果 · ${calculation.label}` })),
  ]
}
