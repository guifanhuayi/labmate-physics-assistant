<script setup lang="ts">
import { computed, ref, toRaw, watch } from 'vue'
import { ApiError, managementApi, type TemplateView } from '../api/client'
import SpreadsheetTableEditor from './SpreadsheetTableEditor.vue'
import PhysicsNotationInput from './PhysicsNotationInput.vue'
import { renderPhysicsNotation } from '../templates/physicsNotation'
import {
  createBlankTemplate,
  createMeasurementField,
  createMechanicsTemplate,
  createSpreadsheetGrid,
  normalizeTemplateSchema,
  PHYSICS_SYMBOLS,
  resizeSpreadsheetGrid,
  schemaValueOptions,
  type TemplateCalculation,
  type TemplateChart,
  type TemplateField,
  type TemplateSchema,
  type TemplateTable,
} from '../templates/designer'

const props = defineProps<{ templates: TemplateView[] }>()
const emit = defineEmits<{ refresh: []; published: [versionId: string] }>()

const draft = ref<TemplateSchema>(createMechanicsTemplate())
const tableEditors = ref<Array<{ flush?: () => Promise<void> }>>([])
const editorSession = ref(0)
watch(draft, () => { editorSession.value++ })
const selectedTemplateId = ref('')
const busy = ref(false)
const status = ref('已根据《力学综合实验》报告整理出操作步骤、4 张数据表和 3 张图表。')
const error = ref('')
const validationIssues = ref<{ path: string; message: string }[]>([])
const importWarnings = ref<string[]>([])
const newTableRows = ref(5)
const newTableColumns = ref(3)
const valueOptions = computed(() => schemaValueOptions(draft.value))
const artifactOptions = [
  { value: 'data_image', label: '原始数据图片' },
  { value: 'charts', label: '数据图表' },
  { value: 'excel', label: 'Excel 数据文件' },
  { value: 'conclusion', label: '实验结论' },
]
const calculationFunctions = ['MEAN', 'STD', 'ABS', 'SQRT', 'POW', 'LINEAR_SLOPE', 'LINEAR_INTERCEPT', 'R_SQUARED'] as const
const physicsSymbols = PHYSICS_SYMBOLS

function reportError(value: unknown) {
  error.value = value instanceof ApiError ? value.message : value instanceof Error ? value.message : '操作失败，请稍后再试。'
  status.value = ''
}

function useMechanicsPreset() {
  selectedTemplateId.value = ''
  draft.value = createMechanicsTemplate()
  validationIssues.value = []
  importWarnings.value = []
  error.value = ''
  status.value = '已载入力学综合实验预设，可直接修改后保存。'
}

function useBlankTemplate() {
  selectedTemplateId.value = ''
  draft.value = createBlankTemplate()
  validationIssues.value = []
  importWarnings.value = []
  error.value = ''
  status.value = '已创建空白模板。'
}

function editTemplate(item: TemplateView) {
  selectedTemplateId.value = item.id
  draft.value = normalizeTemplateSchema(structuredClone(toRaw(item.schema)), item.name, item.description)
  validationIssues.value = []
  importWarnings.value = []
  error.value = ''
  status.value = `正在编辑“${item.name}”的草稿；已发布版本不会被改变。`
}

async function importWord(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  busy.value = true
  error.value = ''
  status.value = ''
  importWarnings.value = []
  try {
    const result = await managementApi.importWordTemplate(file)
    selectedTemplateId.value = ''
    draft.value = normalizeTemplateSchema(result.schema, file.name.replace(/\.docx$/i, ''), '')
    validationIssues.value = []
    importWarnings.value = result.warnings
    status.value = `已从“${file.name}”生成可编辑草稿。请核对测量名称、符号和单位，再保存并检查。`
  } catch (value) {
    reportError(value)
  } finally {
    busy.value = false
  }
}

async function importExcel(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  busy.value = true
  error.value = ''
  importWarnings.value = []
  try {
    const result = await managementApi.importExcelTemplate(file)
    const usedIds = new Set(draft.value.tables.map((item) => item.id))
    for (const source of normalizeTemplateSchema(result.schema, '', '').tables) {
      let id = source.id
      let suffix = 2
      while (usedIds.has(id)) id = `${source.id}_${suffix++}`
      usedIds.add(id)
      const keyMap = new Map(source.fields.map((field, index) => [field.key, `${id}_field_${index + 1}`]))
      source.id = id
      source.fields.forEach((field) => { field.key = keyMap.get(field.key) || field.key })
      source.grid?.cells.forEach((cell) => { if (cell.fieldKey) cell.fieldKey = keyMap.get(cell.fieldKey) || cell.fieldKey })
      draft.value.tables.push(source)
    }
    importWarnings.value = result.warnings
    status.value = `已从“${file.name}”添加 ${result.schema.tables instanceof Array ? result.schema.tables.length : 0} 张表格。请核对后保存。`
  } catch (value) {
    reportError(value)
  } finally {
    busy.value = false
  }
}

async function removeTemplate(item: TemplateView) {
  if (!window.confirm(`确认删除模板“${item.name}”吗？\n\n它将从模板列表移除，已发布任务和历史数据会保留。`)) return
  busy.value = true
  error.value = ''
  try {
    await managementApi.deleteTemplate(item.id)
    if (selectedTemplateId.value === item.id) useBlankTemplate()
    status.value = `模板“${item.name}”已从列表移除。`
    await emit('refresh')
  } catch (value) {
    reportError(value)
  } finally {
    busy.value = false
  }
}

function addStep() {
  const index = draft.value.steps.length + 1
  draft.value.steps.push({ id: `step_${index}`, title: `实验步骤 ${index}`, instruction: '' })
}

function addTable() {
  const used = new Set(draft.value.tables.map((item) => item.id))
  let index = 1
  while (used.has(`table_${index}`)) index += 1
  const rows = Math.max(1, Math.min(200, Math.round(Number(newTableRows.value) || 1)))
  const columns = Math.max(1, Math.min(30, Math.round(Number(newTableColumns.value) || 1)))
  const id = `table_${index}`
  const fields: TemplateField[] = []
  for (let column = 0; column < columns; column += 1) fields.push(createMeasurementField(id, column, fields))
  draft.value.tables.push({
    id,
    title: `数据记录表 ${index}`,
    description: '',
    minimumRows: rows,
    maximumRows: rows,
    fields,
    grid: createSpreadsheetGrid(fields, rows),
  })
}

function addField(table: TemplateTable) {
  table.fields.push(createMeasurementField(table.id, table.fields.length, table.fields))
  if (table.grid && table.grid.columns < table.fields.length) {
    table.grid = resizeSpreadsheetGrid(table.grid, table.grid.rows, table.fields.length, table.fields)
  }
}

function syncGridBindings(table: TemplateTable) {
  if (!table.grid) return
  const keys = new Set(table.fields.map((field) => field.key))
  for (const cell of table.grid.cells) {
    if (cell.kind === 'field' && (!cell.fieldKey || !keys.has(cell.fieldKey))) {
      const replacement = table.fields[cell.column] || table.fields[0]
      if (replacement) cell.fieldKey = replacement.key
      else {
        cell.kind = 'label'
        delete cell.fieldKey
      }
    }
  }
}

function removeField(table: TemplateTable, fieldIndex: number) {
  if (table.fields.length <= 1) return
  table.fields.splice(fieldIndex, 1)
  syncGridBindings(table)
}

function appendFieldSymbol(field: TemplateField, symbol: string) {
  field.symbol = `${field.symbol || ''}${symbol}`
}

function renameMeasurement(table: TemplateTable, field: TemplateField, column: number, value: string) {
  const former = field.label
  field.label = value
  const heading = table.grid?.cells.find((cell) => cell.row === 0 && cell.column === column && cell.kind === 'label' && cell.rowSpan === 1 && cell.colSpan === 1)
  if (heading && heading.text === former) heading.text = value
}

function updateEnumOptions(field: TemplateField, value: string) {
  field.options = value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean)
}

function toggleCalculationArgument(calculation: TemplateCalculation, key: string) {
  const index = calculation.args.indexOf(key)
  if (index >= 0) calculation.args.splice(index, 1)
  else calculation.args.push(key)
}

function calculationPreview(calculation: TemplateCalculation) {
  const labels = calculation.args.map((key) => valueOptions.value.find((item) => item.key === key)?.label || key)
  return `${calculation.symbol || calculation.label} = ${calculation.function}(${labels.join(', ') || '请选择变量'})`
}

function addCalculation() {
  const first = valueOptions.value[0]?.key || ''
  const item: TemplateCalculation = {
    key: `calculation_${draft.value.calculations.length + 1}`,
    label: `计算结果 ${draft.value.calculations.length + 1}`,
    function: 'MEAN',
    args: first ? [first] : [],
    unit: '1',
  }
  draft.value.calculations.push(item)
}

function addChart() {
  const first = valueOptions.value[0]?.key || ''
  const second = valueOptions.value[1]?.key || first
  const chart: TemplateChart = { title: `图表 ${draft.value.charts.length + 1}`, type: 'scatter', x: first, y: second }
  draft.value.charts.push(chart)
}

function syncChecks() {
  draft.value.checks = draft.value.tables.map((table) => ({ type: 'minimum_rows', tableId: table.id, value: table.minimumRows }))
}

async function saveAndValidate() {
  busy.value = true
  error.value = ''
  status.value = ''
  validationIssues.value = []
  try {
    await Promise.all(tableEditors.value.map(editor => editor.flush?.()))
    syncChecks()
    let templateId = selectedTemplateId.value
    if (!templateId) {
      const created = await managementApi.createTemplate(draft.value.title, draft.value.description)
      templateId = created.id
      selectedTemplateId.value = templateId
    }
    await managementApi.saveTemplate(templateId, draft.value.title, draft.value.description, draft.value as unknown as Record<string, unknown>)
    const validation = await managementApi.validateTemplate(templateId)
    validationIssues.value = validation.issues
    status.value = validation.valid ? '草稿已保存并通过发布校验。' : `草稿已保存，还有 ${validation.issues.length} 项需要修正。`
    await emit('refresh')
    return validation.valid
  } catch (value) {
    reportError(value)
    return false
  } finally {
    busy.value = false
  }
}

async function publishDraft() {
  const valid = await saveAndValidate()
  if (!valid || !selectedTemplateId.value) return
  busy.value = true
  try {
    const version = await managementApi.publishTemplate(selectedTemplateId.value)
    status.value = `模板 v${version.versionNumber} 已发布；这个版本快照不可修改。`
    emit('published', version.id)
    await emit('refresh')
  } catch (value) {
    reportError(value)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="template-designer">
    <aside class="designer-sidebar">
      <div class="panel-heading"><p>01</p><h2>选择起点</h2></div>
      <button class="preset-card active-preset" type="button" @click="useMechanicsPreset">
        <strong>力学综合实验</strong>
        <span>从上传的实验报告提取，含步骤、4 张数据表和图表要求</span>
      </button>
      <button class="preset-card" type="button" @click="useBlankTemplate">
        <strong>空白实验</strong>
        <span>从一个步骤和一张数据表开始</span>
      </button>
      <label class="preset-card word-import-card" for="word-template-file">
        <strong>导入 Word 实验模板</strong>
        <span>选择 .docx 文件，自动提取实验名称、操作文字和数据表，生成可编辑草稿</span>
        <input id="word-template-file" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" :disabled="busy" @change="importWord" />
      </label>

      <div class="sidebar-section">
        <h3>已有模板</h3>
        <div v-for="item in props.templates" :key="item.id" class="template-list-item">
          <button class="template-list-button" :class="{ 'selected-template': selectedTemplateId === item.id }" :aria-pressed="selectedTemplateId === item.id" type="button" :disabled="busy" @click="editTemplate(item)">
            <strong>{{ item.name }}</strong>
            <span>{{ item.versionCount ? `已发布 v${item.versionCount}` : '草稿' }} · 点击查看和编辑</span>
          </button>
          <button class="template-delete-button" type="button" :disabled="busy" :aria-label="`删除模板 ${item.name}`" @click="removeTemplate(item)">删除</button>
        </div>
        <p v-if="!props.templates.length" class="muted-copy">还没有已保存的模板。</p>
      </div>
    </aside>

    <div class="designer-main">
      <div class="designer-toolbar">
        <div><p class="eyebrow">可视化实验模板</p><h2>{{ draft.title }}</h2></div>
        <div class="toolbar-actions">
          <button class="secondary-button save-button compact-button" type="button" :disabled="busy" @click="saveAndValidate">保存并检查</button>
          <button class="primary-button compact-button" type="button" :disabled="busy" @click="publishDraft">发布新版本</button>
        </div>
      </div>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <p v-if="status" class="success-message" role="status">{{ status }}</p>
      <ul v-if="importWarnings.length" class="validation-list" aria-label="导入待核对项">
        <li v-for="warning in importWarnings" :key="warning">{{ warning }}</li>
      </ul>
      <ul v-if="validationIssues.length" class="validation-list">
        <li v-for="issue in validationIssues" :key="`${issue.path}-${issue.message}`"><code>{{ issue.path }}</code>{{ issue.message }}</li>
      </ul>

      <section class="designer-section information-section">
        <div class="section-title"><span>1</span><div><h3>实验基本信息</h3><p>学生看到的实验名称、目的和说明。</p></div></div>
        <label>实验名称</label><input v-model="draft.title" required />
        <label>实验说明</label><textarea v-model="draft.description" rows="3" />
        <label>实验目标（每行一项）</label>
        <textarea :value="draft.objectives.join('\n')" rows="4" @input="draft.objectives = ($event.target as HTMLTextAreaElement).value.split('\n').filter(Boolean)" />
        <label>预习与讨论问题（每行一题）</label>
        <textarea :value="draft.preparationQuestions.join('\n')" rows="6" @input="draft.preparationQuestions = ($event.target as HTMLTextAreaElement).value.split('\n').filter(Boolean)" />
        <label>实验后讨论问题（每行一题）</label>
        <textarea :value="draft.discussionQuestions.join('\n')" rows="6" @input="draft.discussionQuestions = ($event.target as HTMLTextAreaElement).value.split('\n').filter(Boolean)" />
      </section>

      <section class="designer-section steps-section">
        <div class="section-title"><span>2</span><div><h3>实验操作步骤</h3><p>把操作说明和对应数据表绑定，学生按顺序完成。</p></div></div>
        <article v-for="(step, index) in draft.steps" :key="step.id" class="editor-card">
          <div class="editor-card-heading"><strong>步骤 {{ index + 1 }}</strong><button class="text-danger" type="button" @click="draft.steps.splice(index, 1)">移除</button></div>
          <div class="three-fields">
            <div><label>步骤标识</label><input v-model="step.id" /></div>
            <div><label>步骤名称</label><input v-model="step.title" /></div>
            <div><label>关联数据表</label><select v-model="step.tableId"><option value="">不关联</option><option v-for="table in draft.tables" :key="table.id" :value="table.id">{{ table.title }}</option></select></div>
          </div>
          <label>操作说明</label><textarea v-model="step.instruction" rows="2" />
        </article>
        <button class="add-button" type="button" @click="addStep">＋ 添加实验步骤</button>
      </section>

      <section class="designer-section data-section">
        <div class="section-title"><span>3</span><div><h3>需要记录的数据</h3><p>每张表按“每行一个测量条件”配置，更适合手机录入。</p></div></div>
        <div class="table-create-controls">
          <label>新表格数据行数<input v-model.number="newTableRows" aria-label="新表格数据行数" type="number" min="1" max="200" /></label>
          <label>新表格测量列数<input v-model.number="newTableColumns" aria-label="新表格测量列数" type="number" min="1" max="30" /></label>
          <button class="add-button add-table-button" type="button" @click="addTable">＋ 按行列数添加数据表</button>
          <label class="excel-import-button" for="excel-template-file">导入 Excel 表格<input id="excel-template-file" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" :disabled="busy" @change="importExcel" /></label>
        </div>
        <p class="field-help">添加后直接填写每列的测量名称、符号、单位和录入类型；行列数也可以在表格内继续调整。</p>
        <article v-for="(table, tableIndex) in draft.tables" :key="table.id" class="editor-card table-editor">
          <div class="editor-card-heading"><strong>数据表 {{ tableIndex + 1 }} · {{ table.title }} · {{ (table.grid?.rows || table.minimumRows + 1) - 1 }} 行 × {{ table.grid?.columns || table.fields.length }} 列</strong><button class="text-danger" type="button" @click="draft.tables.splice(tableIndex, 1)">移除</button></div>
          <label>数据表名称</label><input v-model="table.title" />
          <label>测量说明</label><input v-model="table.description" />
          <SpreadsheetTableEditor :key="`${editorSession}:${table.id}`" ref="tableEditors" v-model="draft.tables[tableIndex]" />
          <div class="field-editor-header"><strong>每列记录什么</strong><span>先填写名称与符号，学生录入时会按此显示。</span></div>
          <div v-for="(field, fieldIndex) in table.fields" :key="`${table.id}-${fieldIndex}`" class="measurement-card">
            <div class="measurement-card-heading"><strong>第 {{ fieldIndex + 1 }} 列</strong><button class="text-danger" type="button" :disabled="table.fields.length <= 1" :aria-label="`删除测量项 ${field.label}`" @click="removeField(table, fieldIndex)">删除这一项</button></div>
            <div class="measurement-main">
              <PhysicsNotationInput :model-value="field.label" label="测量名称" placeholder="例如：电压、平均速度" @update:model-value="renameMeasurement(table, field, fieldIndex, $event || '')" />
              <PhysicsNotationInput v-model="field.symbol" label="测量符号" placeholder="如 v_0、\Delta x" />
              <PhysicsNotationInput v-model="field.unit" label="单位" placeholder="如 m/s^2、\Omega" />
              <label>录入类型<select v-model="field.type" aria-label="录入类型"><option value="number">数值</option><option value="integer">整数</option><option value="text">文本</option><option value="enum">选项</option><option value="time">时间</option><option value="image">图片</option></select></label>
            </div>
            <div class="measurement-options">
              <label><input v-model="field.required" type="checkbox" />学生必须填写</label>
              <label>数据归属<select v-model="field.scope" aria-label="数据归属"><option value="individual">个人记录</option><option value="group">组内共享</option></select></label>
              <details class="field-symbol-picker">
                <summary>选常用符号</summary>
                <div><button v-for="symbol in physicsSymbols" :key="symbol" type="button" @click="appendFieldSymbol(field, symbol)">{{ symbol }}</button></div>
                <small>电脑键盘输入反斜杠可选择符号；下标用 _，上标用 ^，例如 x_&#123;max&#125;。</small>
              </details>
            </div>
            <details class="measurement-advanced">
              <summary>更多设置：精度、范围、提示与内部编号</summary>
              <div class="measurement-main">
                <label>小数位<input v-model.number="field.precision" aria-label="小数位" type="number" min="0" max="8" /></label>
                <label>下限<input v-model.number="field.min" aria-label="下限" type="number" /></label>
                <label>上限<input v-model.number="field.max" aria-label="上限" type="number" /></label>
                <label>内部编号<input v-model="field.key" aria-label="内部编号" @change="syncGridBindings(table)" /></label>
              </div>
              <label v-if="field.type === 'enum'">可选内容（逗号或换行分隔）<textarea :value="field.options?.join('，')" rows="2" @input="updateEnumOptions(field, ($event.target as HTMLTextAreaElement).value)" /></label>
              <label>学生端提示<input v-model="field.description" placeholder="例如：读数稳定后记录" /></label>
            </details>
          </div>
          <button class="add-button compact-add" type="button" @click="addField(table)">＋ 添加测量项</button>
        </article>
      </section>

      <section class="designer-section calculation-section">
        <div class="section-title"><span>4</span><div><h3>公式与计算结果</h3><p>选择测量数据组成公式，无需输入内部编号或复杂符号。</p></div></div>
        <article v-for="(calculation, index) in draft.calculations" :key="`${calculation.key}-${index}`" class="editor-card">
          <div class="editor-card-heading"><strong>{{ calculation.label }}</strong><button class="text-danger" type="button" @click="draft.calculations.splice(index, 1)">移除</button></div>
          <div class="four-fields">
            <div><label>结果名称</label><input v-model="calculation.label" /></div>
            <div><label>结果键</label><input v-model="calculation.key" /></div>
            <div><label>函数</label><select v-model="calculation.function"><option v-for="fn in calculationFunctions" :key="fn" :value="fn">{{ fn }}</option></select></div>
            <PhysicsNotationInput v-model="calculation.unit" label="单位" />
          </div>
          <PhysicsNotationInput v-model="calculation.symbol" label="结果符号" placeholder="如 R、T^2" />
          <PhysicsNotationInput v-model="calculation.formulaText" label="公式写法（保存到模板，暂不参与自动计算）" placeholder="如 \bar{x}=\frac{1}{n}\sum_{i=1}^{n}x_i" />
          <label>点击插入或移除变量</label>
          <div class="formula-variable-palette">
            <button v-for="option in valueOptions.filter((item) => item.key !== calculation.key)" :key="option.key" type="button" :class="{ active: calculation.args.includes(option.key) }" @click="toggleCalculationArgument(calculation, option.key)">{{ option.label }}</button>
          </div>
          <div class="formula-preview" aria-live="polite">{{ calculationPreview(calculation) }}</div>
          <div v-if="calculation.function === 'POW'"><label>指数</label><input :value="calculation.parameters?.[0] ?? 2" type="number" @input="calculation.parameters = [Number(($event.target as HTMLInputElement).value)]" /></div>
        </article>
        <button class="add-button" type="button" @click="addCalculation">＋ 添加计算</button>
      </section>

      <section class="designer-section requirements-section">
        <div class="section-title"><span>5</span><div><h3>图表与提交要求</h3><p>选择横纵坐标和拟合方式，同时指定学生需要提交的结果。</p></div></div>
        <article v-for="(chart, index) in draft.charts" :key="`${chart.title}-${index}`" class="editor-card chart-editor">
          <input v-model="chart.title" aria-label="图表名称" placeholder="图表名称" />
          <select v-model="chart.type" aria-label="图表类型"><option value="scatter">散点图</option><option value="line">折线图</option></select>
          <select v-model="chart.x" aria-label="横坐标"><option v-for="option in valueOptions" :key="option.key" :value="option.key">X · {{ option.label }}</option></select>
          <select v-model="chart.y" aria-label="纵坐标"><option v-for="option in valueOptions" :key="option.key" :value="option.key">Y · {{ option.label }}</option></select>
          <label class="inline-check"><input v-model="chart.fit" type="checkbox" true-value="linear" :false-value="undefined" />线性拟合</label>
          <button class="icon-danger" type="button" aria-label="删除图表" @click="draft.charts.splice(index, 1)">×</button>
        </article>
        <button class="add-button compact-add" type="button" @click="addChart">＋ 添加图表</button>
        <div class="artifact-options">
          <label v-for="option in artifactOptions" :key="option.value" class="check-card"><input v-model="draft.requiredArtifacts" type="checkbox" :value="option.value" /><span>{{ option.label }}</span></label>
        </div>
      </section>

      <section class="designer-section preview-section">
        <div class="section-title"><span>6</span><div><h3>学生端预览</h3><p>发布前快速确认步骤顺序、表头和记录规模。</p></div></div>
        <div class="student-preview">
          <h3>{{ draft.title }}</h3><p>{{ draft.description }}</p>
          <ol><li v-for="step in draft.steps" :key="step.id"><strong>{{ step.title }}</strong><span>{{ step.instruction }}</span></li></ol>
          <article v-for="table in draft.tables" :key="table.id">
            <div><strong>{{ table.title }}</strong><span>{{ table.minimumRows === table.maximumRows ? `${table.minimumRows} 行` : `${table.minimumRows}—${table.maximumRows} 行` }}</span></div>
            <div class="preview-table-scroll"><table><thead><tr><th>#</th><th v-for="field in table.fields" :key="field.key"><span v-html="renderPhysicsNotation(field.label)" /><small v-html="renderPhysicsNotation(`${field.symbol} / ${field.unit}`)" /></th></tr></thead><tbody><tr><td>1</td><td v-for="field in table.fields" :key="field.key">—</td></tr></tbody></table></div>
          </article>
        </div>
      </section>

      <div class="designer-footer">
        <span>保存草稿不会影响已发布版本；发布会生成新的不可变快照。</span>
      </div>
    </div>
  </div>
</template>
