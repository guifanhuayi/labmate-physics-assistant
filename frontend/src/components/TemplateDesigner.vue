<script setup lang="ts">
import { computed, ref } from 'vue'
import { ApiError, managementApi, type TemplateView } from '../api/client'
import SpreadsheetTableEditor from './SpreadsheetTableEditor.vue'
import {
  createBlankTemplate,
  createMechanicsTemplate,
  normalizeTemplateSchema,
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
const selectedTemplateId = ref('')
const busy = ref(false)
const status = ref('已根据《力学综合实验》报告整理出操作步骤、4 张数据表和 3 张图表。')
const error = ref('')
const validationIssues = ref<{ path: string; message: string }[]>([])
const valueOptions = computed(() => schemaValueOptions(draft.value))
const artifactOptions = [
  { value: 'data_image', label: '原始数据图片' },
  { value: 'charts', label: '数据图表' },
  { value: 'excel', label: 'Excel 数据文件' },
  { value: 'conclusion', label: '实验结论' },
]
const calculationFunctions = ['MEAN', 'STD', 'ABS', 'SQRT', 'POW', 'LINEAR_SLOPE', 'LINEAR_INTERCEPT', 'R_SQUARED'] as const

function reportError(value: unknown) {
  error.value = value instanceof ApiError ? value.message : value instanceof Error ? value.message : '操作失败，请稍后再试。'
  status.value = ''
}

function useMechanicsPreset() {
  selectedTemplateId.value = ''
  draft.value = createMechanicsTemplate()
  validationIssues.value = []
  error.value = ''
  status.value = '已载入力学综合实验预设，可直接修改后保存。'
}

function useBlankTemplate() {
  selectedTemplateId.value = ''
  draft.value = createBlankTemplate()
  validationIssues.value = []
  error.value = ''
  status.value = '已创建空白模板。'
}

function editTemplate(item: TemplateView) {
  selectedTemplateId.value = item.id
  draft.value = normalizeTemplateSchema(structuredClone(item.schema), item.name, item.description)
  validationIssues.value = []
  error.value = ''
  status.value = `正在编辑“${item.name}”的草稿；已发布版本不会被改变。`
}

function addStep() {
  const index = draft.value.steps.length + 1
  draft.value.steps.push({ id: `step_${index}`, title: `实验步骤 ${index}`, instruction: '' })
}

function addTable() {
  const index = draft.value.tables.length + 1
  draft.value.tables.push({
    id: `table_${index}`,
    title: `数据记录表 ${index}`,
    description: '',
    minimumRows: 1,
    maximumRows: 10,
    fields: [{ key: `value_${index}_1`, label: '测量值', symbol: 'x', type: 'number', unit: '1', precision: 2, required: true }],
  })
}

function addField(table: TemplateTable) {
  const index = table.fields.length + 1
  table.fields.push({ key: `${table.id}_field_${index}`, label: `字段 ${index}`, symbol: '', type: 'number', unit: '1', precision: 2, required: true })
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
  table.fields.splice(fieldIndex, 1)
  syncGridBindings(table)
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

      <div class="sidebar-section">
        <h3>已有模板</h3>
        <button v-for="item in props.templates" :key="item.id" class="template-list-button" type="button" @click="editTemplate(item)">
          <strong>{{ item.name }}</strong>
          <span>{{ item.versionCount ? `已发布 v${item.versionCount}` : '草稿' }}</span>
        </button>
        <p v-if="!props.templates.length" class="muted-copy">还没有已保存的模板。</p>
      </div>
    </aside>

    <div class="designer-main">
      <div class="designer-toolbar">
        <div><p class="eyebrow">可视化实验模板</p><h2>{{ draft.title }}</h2></div>
        <div class="toolbar-actions">
          <button class="secondary-button compact-button" type="button" :disabled="busy" @click="saveAndValidate">保存并检查</button>
          <button class="primary-button compact-button" type="button" :disabled="busy" @click="publishDraft">发布新版本</button>
        </div>
      </div>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <p v-if="status" class="success-message" role="status">{{ status }}</p>
      <ul v-if="validationIssues.length" class="validation-list">
        <li v-for="issue in validationIssues" :key="`${issue.path}-${issue.message}`"><code>{{ issue.path }}</code>{{ issue.message }}</li>
      </ul>

      <section class="designer-section">
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

      <section class="designer-section">
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

      <section class="designer-section">
        <div class="section-title"><span>3</span><div><h3>需要记录的数据</h3><p>每张表按“每行一个测量条件”配置，更适合手机录入。</p></div></div>
        <article v-for="(table, tableIndex) in draft.tables" :key="table.id" class="editor-card table-editor">
          <div class="editor-card-heading"><strong>数据表 {{ tableIndex + 1 }} · {{ table.title }}</strong><button class="text-danger" type="button" @click="draft.tables.splice(tableIndex, 1)">移除</button></div>
          <div class="two-fields"><div><label>数据表标识</label><input v-model="table.id" /></div><div><label>数据表名称</label><input v-model="table.title" /></div></div>
          <label>测量说明</label><input v-model="table.description" />
          <SpreadsheetTableEditor v-model="draft.tables[tableIndex]" />
          <div class="field-editor-header"><strong>记录字段定义</strong><span>表格中的数据输入格绑定这些字段</span></div>
          <div v-for="(field, fieldIndex) in table.fields" :key="`${table.id}-${fieldIndex}`" class="field-editor-row">
            <input v-model="field.label" aria-label="字段名称" placeholder="字段名称" />
            <input v-model="field.key" aria-label="字段键" placeholder="field_key" @change="syncGridBindings(table)" />
            <select v-model="field.type" aria-label="数据类型"><option value="number">数值</option><option value="integer">整数</option><option value="text">文本</option></select>
            <input v-model="field.symbol" aria-label="符号" placeholder="符号" />
            <input v-model="field.unit" aria-label="单位" placeholder="单位" />
            <input v-model.number="field.precision" aria-label="小数位" type="number" min="0" max="8" />
            <input v-model.number="field.min" aria-label="下限" type="number" placeholder="下限" />
            <input v-model.number="field.max" aria-label="上限" type="number" placeholder="上限" />
            <label class="field-required"><input v-model="field.required" type="checkbox" />必填</label>
            <button class="icon-danger" type="button" aria-label="删除字段" @click="removeField(table, fieldIndex)">×</button>
          </div>
          <button class="add-button compact-add" type="button" @click="addField(table)">＋ 添加字段</button>
        </article>
        <button class="add-button" type="button" @click="addTable">＋ 添加数据表</button>
      </section>

      <section class="designer-section">
        <div class="section-title"><span>4</span><div><h3>自动计算</h3><p>只选择受控函数和已有字段，不需要编写公式代码。</p></div></div>
        <article v-for="(calculation, index) in draft.calculations" :key="`${calculation.key}-${index}`" class="editor-card">
          <div class="editor-card-heading"><strong>{{ calculation.label }}</strong><button class="text-danger" type="button" @click="draft.calculations.splice(index, 1)">移除</button></div>
          <div class="four-fields">
            <div><label>结果名称</label><input v-model="calculation.label" /></div>
            <div><label>结果键</label><input v-model="calculation.key" /></div>
            <div><label>函数</label><select v-model="calculation.function"><option v-for="fn in calculationFunctions" :key="fn" :value="fn">{{ fn }}</option></select></div>
            <div><label>单位</label><input v-model="calculation.unit" /></div>
          </div>
          <label>参与计算的字段</label>
          <select v-model="calculation.args" multiple class="multi-select"><option v-for="option in valueOptions.filter((item) => item.key !== calculation.key)" :key="option.key" :value="option.key">{{ option.label }}</option></select>
          <div v-if="calculation.function === 'POW'"><label>指数</label><input :value="calculation.parameters?.[0] ?? 2" type="number" @input="calculation.parameters = [Number(($event.target as HTMLInputElement).value)]" /></div>
        </article>
        <button class="add-button" type="button" @click="addCalculation">＋ 添加计算</button>
      </section>

      <section class="designer-section">
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
            <div class="preview-table-scroll"><table><thead><tr><th>#</th><th v-for="field in table.fields" :key="field.key">{{ field.label }}<small>{{ field.symbol }} / {{ field.unit }}</small></th></tr></thead><tbody><tr><td>1</td><td v-for="field in table.fields" :key="field.key">—</td></tr></tbody></table></div>
          </article>
        </div>
      </section>

      <div class="designer-footer">
        <span>保存草稿不会影响已发布版本；发布会生成新的不可变快照。</span>
        <div class="toolbar-actions"><button class="secondary-button compact-button" type="button" :disabled="busy" @click="saveAndValidate">保存并检查</button><button class="primary-button compact-button" type="button" :disabled="busy" @click="publishDraft">发布新版本</button></div>
      </div>
    </div>
  </div>
</template>
