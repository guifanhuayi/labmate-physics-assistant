<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import BrandLockup from '../components/BrandLockup.vue'
import TemplateDesigner from '../components/TemplateDesigner.vue'
import AssignmentGroups from '../components/AssignmentGroups.vue'
import { ApiError, managementApi, type AssignmentView, type ClassView, type ImportPreview, type StudentView, type TemplateView, type TeacherView } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const isTeacher = computed(() => auth.user?.role === 'teacher')
const classes = ref<ClassView[]>([])
const teachers = ref<TeacherView[]>([])
const classStudents = ref<StudentView[]>([])
const selectedClassId = ref('')
const studentsLoading = ref(false)
const templates = ref<TemplateView[]>([])
const assignments = ref<AssignmentView[]>([])
const deletedAssignments = ref<AssignmentView[]>([])
const busy = ref(false)
const message = ref('')
const error = ref('')
const activeSection = ref<'classes' | 'templates' | 'assignments'>('classes')
const classForm = reactive({ classCode: 'PHY2401', className: '物理2401', semester: '2026秋', teacherId: '' })
const rosterClassId = ref('')
const rosterFile = ref<File | null>(null)
const rosterPreview = ref<ImportPreview | null>(null)
const assignment = reactive({ templateVersionId: '', classId: '', title: '实验一：伏安法测电阻', startAt: '', dueAt: '', groupSharingEnabled: false })
const expandedAssignmentId = ref('')

function showError(value: unknown) {
  error.value = value instanceof ApiError ? value.message : '操作失败，请稍后再试。'
  message.value = ''
}

async function loadData() {
  try {
    classes.value = await managementApi.listClasses()
    if (!isTeacher.value) teachers.value = await managementApi.listTeachers()
    if (isTeacher.value) {
      templates.value = await managementApi.listTemplates()
      assignments.value = await managementApi.listAssignments()
      deletedAssignments.value = await managementApi.listDeletedAssignments()
      if (assignment.templateVersionId && !templates.value.some((item) => item.latestVersionId === assignment.templateVersionId)) {
        assignment.templateVersionId = ''
      }
    }
    if (!rosterClassId.value && classes.value[0]) rosterClassId.value = classes.value[0].id
    if (!assignment.classId && classes.value[0]) assignment.classId = classes.value[0].id
    if (rosterClassId.value && !classes.value.some((item) => item.id === rosterClassId.value)) {
      rosterClassId.value = classes.value[0]?.id || ''
    }
    if (assignment.classId && !classes.value.some((item) => item.id === assignment.classId)) {
      assignment.classId = classes.value[0]?.id || ''
    }
    if (selectedClassId.value && !classes.value.some((item) => item.id === selectedClassId.value)) {
      selectedClassId.value = ''
      classStudents.value = []
    }
  } catch (value) { showError(value) }
}

async function createClass() {
  busy.value = true; error.value = ''; message.value = ''
  try {
    await managementApi.createClass({
      classCode: classForm.classCode, className: classForm.className, semester: classForm.semester,
      ...(isTeacher.value ? {} : { teacherId: classForm.teacherId }),
    })
    message.value = '班级已创建。'
    await loadData()
  } catch (value) { showError(value) } finally { busy.value = false }
}

async function loadClassStudents(classId: string) {
  selectedClassId.value = classId
  studentsLoading.value = true
  try {
    classStudents.value = await managementApi.listClassStudents(classId)
  } catch (value) {
    selectedClassId.value = ''
    classStudents.value = []
    showError(value)
  } finally {
    studentsLoading.value = false
  }
}

async function toggleClassStudents(item: ClassView) {
  if (selectedClassId.value === item.id) {
    selectedClassId.value = ''
    classStudents.value = []
    return
  }
  await loadClassStudents(item.id)
}

async function removeClass(item: ClassView) {
  const confirmed = window.confirm(`确认删除班级“${item.classCode} · ${item.className}”吗？\n\n班级成员关系和名单预览将被删除，学生账号会保留。`)
  if (!confirmed) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    await managementApi.deleteClass(item.id)
    if (selectedClassId.value === item.id) {
      selectedClassId.value = ''
      classStudents.value = []
    }
    if (rosterClassId.value === item.id) rosterClassId.value = ''
    if (assignment.classId === item.id) assignment.classId = ''
    message.value = `班级“${item.className}”已删除，学生账号已保留。`
    await loadData()
  } catch (value) { showError(value) } finally { busy.value = false }
}

function pickFile(event: Event) {
  rosterFile.value = (event.target as HTMLInputElement).files?.[0] || null
  rosterPreview.value = null
}

async function previewRoster() {
  if (!rosterClassId.value || !rosterFile.value) { error.value = '请选择班级和名单文件。'; return }
  busy.value = true; error.value = ''; message.value = ''
  try {
    rosterPreview.value = await managementApi.previewRoster(rosterClassId.value, rosterFile.value)
    message.value = rosterPreview.value.errorCount ? '预览完成，请先修正错误。' : '预览通过，可以确认导入。'
  } catch (value) { showError(value) } finally { busy.value = false }
}

async function commitRoster() {
  if (!rosterPreview.value) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await managementApi.commitRoster(rosterPreview.value.id)
    message.value = auth.mode?.demoEnabled
      ? `导入完成：新增 ${result.created} 人，新增班级关系 ${result.membershipsAdded} 条。学生可用已导入的学号和任意非空密码演示登录。`
      : `导入完成：新增 ${result.created} 人，新增班级关系 ${result.membershipsAdded} 条；${result.requiresEnrollment} 名学生需用姓名和学号完成首次设置。`
    rosterPreview.value = null
    await loadData()
    if (rosterClassId.value) await loadClassStudents(rosterClassId.value)
  } catch (value) { showError(value) } finally { busy.value = false }
}

async function publishAssignment() {
  if (!assignment.templateVersionId || !assignment.classId || !assignment.startAt || !assignment.dueAt) {
    error.value = '请选择模板版本、班级以及开放和截止时间。'; return
  }
  busy.value = true; error.value = ''; message.value = ''
  try {
    await managementApi.createAssignment({
      templateVersionId: assignment.templateVersionId,
      classId: assignment.classId,
      title: assignment.title,
      startAt: new Date(assignment.startAt).toISOString(),
      dueAt: new Date(assignment.dueAt).toISOString(),
      groupSharingEnabled: assignment.groupSharingEnabled,
    })
    message.value = '实验任务已发布到班级。'
    await loadData()
  } catch (value) { showError(value) } finally { busy.value = false }
}

async function removeAssignment(item: AssignmentView) {
  const purgeDate = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toLocaleDateString('zh-CN')
  const confirmed = window.confirm(`确认删除实验任务“${item.title}”吗？\n\n${item.className}的学生将立即看不到该任务，也不能继续录入。学生草稿、分组及共享数据保留 30 天，期间可以恢复，预计 ${purgeDate} 后永久清理。`)
  if (!confirmed) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await managementApi.deleteAssignment(item.id)
    if (expandedAssignmentId.value === item.id) expandedAssignmentId.value = ''
    message.value = `任务“${item.title}”已移入 30 天保留区，可在 ${new Date(result.purgeAfter).toLocaleString('zh-CN')} 前恢复。`
    await loadData()
  } catch (value) { showError(value) } finally { busy.value = false }
}

async function restoreAssignment(item: AssignmentView) {
  busy.value = true; error.value = ''; message.value = ''
  try {
    await managementApi.restoreAssignment(item.id)
    message.value = `任务“${item.title}”已恢复，学生记录也已恢复可见。`
    await loadData()
  } catch (value) { showError(value) } finally { busy.value = false }
}

function usePublishedVersion(versionId: string) {
  assignment.templateVersionId = versionId
  activeSection.value = 'assignments'
  message.value = '已选中刚发布的模板版本，请补充班级和时间后发布任务。'
  error.value = ''
}

async function signOut() { await auth.logout(); await router.replace('/login') }
onMounted(loadData)
</script>

<template>
  <div class="workspace-page">
    <header class="workspace-header">
      <BrandLockup />
      <nav aria-label="工作台功能">
        <button :class="{ active: activeSection === 'classes' }" @click="activeSection = 'classes'">班级与名单</button>
        <button v-if="isTeacher" :class="{ active: activeSection === 'templates' }" @click="activeSection = 'templates'">实验模板</button>
        <button v-if="isTeacher" :class="{ active: activeSection === 'assignments' }" @click="activeSection = 'assignments'">任务发布</button>
      </nav>
      <div class="account-menu"><span>{{ auth.user?.name }}</span><small>{{ auth.user?.account }}</small><button @click="signOut">退出</button></div>
    </header>
    <main class="workspace-shell management-shell">
      <section class="workspace-intro">
        <div><p class="eyebrow">阶段 0—4</p><h1>{{ isTeacher ? '教师准备工作台' : '管理员工作台' }}</h1><p>班级、名单、模板版本、实验任务和分组均由服务器持久化与授权。</p></div>
        <span class="verified-badge">服务器已验证</span>
      </section>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <p v-if="message" class="success-message" role="status">{{ message }}</p>

      <section v-if="activeSection === 'classes'" class="management-grid">
        <form class="work-panel information-section" @submit.prevent="createClass">
          <div class="panel-heading"><p>01</p><h2>创建班级</h2></div>
          <label>班级代码</label><input v-model="classForm.classCode" required />
          <label>班级名称</label><input v-model="classForm.className" required />
          <label>学期</label><input v-model="classForm.semester" required />
          <template v-if="!isTeacher"><label>负责教师</label><select v-model="classForm.teacherId" required><option value="">请选择教师</option><option v-for="teacher in teachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }} · {{ teacher.account }}</option></select></template>
          <button class="primary-button" :disabled="busy">创建班级</button>
        </form>
        <div class="work-panel data-section">
          <div class="panel-heading"><p>02</p><h2>名单预览与导入</h2></div>
          <label>目标班级</label>
          <select v-model="rosterClassId"><option value="">请选择</option><option v-for="item in classes" :key="item.id" :value="item.id">{{ item.classCode }} · {{ item.className }}</option></select>
          <label>Excel / CSV 名单</label><input type="file" accept=".xlsx,.csv" @change="pickFile" />
          <p class="field-help">名单只需要“学号、姓名”两列；班级由上方选择决定。旧文件中的班级列会被忽略。</p>
          <button class="secondary-button" :disabled="busy" @click="previewRoster">先预览</button>
          <div v-if="rosterPreview" class="preview-box">
            <strong>有效 {{ rosterPreview.validCount }} 行 · 错误 {{ rosterPreview.errorCount }} 项</strong>
            <ul v-if="rosterPreview.errors.length"><li v-for="issue in rosterPreview.errors" :key="`${issue.row}-${issue.field}`">第 {{ issue.row }} 行：{{ issue.message }}</li></ul>
            <button v-else class="primary-button" :disabled="busy" @click="commitRoster">确认导入</button>
          </div>
        </div>
        <div class="work-panel panel-wide preview-section">
          <div class="panel-heading"><p>当前</p><h2>班级列表</h2></div>
          <div class="data-list class-list">
            <article v-for="item in classes" :key="item.id" class="class-card">
              <div class="class-summary">
                <div><strong>{{ item.classCode }} · {{ item.className }}</strong><span>{{ item.semester }} · {{ item.teacherName }} · {{ item.studentCount }} 名学生</span></div>
                <div class="class-actions">
                  <button class="secondary-button compact-button" :disabled="busy" @click="toggleClassStudents(item)">{{ selectedClassId === item.id ? '收起名单' : '查看学生' }}</button>
                  <button class="danger-button compact-button" :disabled="busy" @click="removeClass(item)">删除班级</button>
                </div>
              </div>
              <div v-if="selectedClassId === item.id" class="student-panel">
                <p v-if="studentsLoading">正在读取学生名单…</p>
                <p v-else-if="!classStudents.length">该班级暂时没有学生。</p>
                <div v-else class="table-scroll">
                  <table>
                    <thead><tr><th>序号</th><th>姓名</th><th>学号</th><th v-if="!auth.mode?.demoEnabled">首次设置</th></tr></thead>
                    <tbody><tr v-for="(student, index) in classStudents" :key="student.id"><td>{{ index + 1 }}</td><td>{{ student.name }}</td><td>{{ student.studentNumber }}</td><td v-if="!auth.mode?.demoEnabled">{{ student.enrollmentCompleted ? '已完成' : '待完成' }}</td></tr></tbody>
                  </table>
                </div>
              </div>
            </article>
            <p v-if="!classes.length">尚未创建班级。</p>
          </div>
        </div>
      </section>

      <section v-else-if="activeSection === 'templates'">
        <TemplateDesigner :templates="templates" @refresh="loadData" @published="usePublishedVersion" />
      </section>

      <section v-else class="management-grid">
        <form class="work-panel information-section" @submit.prevent="publishAssignment">
          <div class="panel-heading"><p>01</p><h2>创建班级实验任务</h2></div>
          <label>任务名称</label><input v-model="assignment.title" required />
          <label>已发布模板版本</label><select v-model="assignment.templateVersionId" required><option value="">请选择</option><option v-for="item in templates.filter((value) => value.latestVersionId)" :key="item.id" :value="item.latestVersionId || ''">{{ item.name }} · v{{ item.versionCount }}</option></select>
          <label>目标班级</label><select v-model="assignment.classId" required><option value="">请选择</option><option v-for="item in classes" :key="item.id" :value="item.id">{{ item.classCode }} · {{ item.className }}</option></select>
          <div class="two-fields"><div><label>开放时间</label><input v-model="assignment.startAt" type="datetime-local" required /></div><div><label>截止时间</label><input v-model="assignment.dueAt" type="datetime-local" required /></div></div>
          <label class="checkbox-label"><input v-model="assignment.groupSharingEnabled" type="checkbox" />允许本任务的小组共享模板中标记为“组内共享”的测量数据</label>
          <button class="primary-button" :disabled="busy">发布实验任务</button>
        </form>
        <div class="work-panel requirements-section">
          <div class="panel-heading"><p>02</p><h2>发布前检查</h2></div>
          <ol class="publish-checklist"><li :class="{ done: assignment.templateVersionId }">使用已发布且不可变的模板版本</li><li :class="{ done: assignment.classId }">选择接收任务的班级</li><li :class="{ done: assignment.startAt && assignment.dueAt }">设置开放和截止时间</li></ol>
          <p class="field-help">任务发布后，学生始终引用选定的模板版本；以后修改模板不会改变已发布任务。</p>
        </div>
        <div class="work-panel panel-wide data-section">
          <div class="panel-heading"><p>当前</p><h2>实验任务</h2></div>
          <div class="assignment-list">
            <article v-for="item in assignments" :key="item.id" class="assignment-with-groups">
              <div><strong>{{ item.title }}</strong><span>{{ item.classCode }} · {{ item.className }}　{{ item.templateName }} v{{ item.versionNumber }} · {{ item.groupSharingEnabled ? '组内共享已开启' : '个人录入' }}</span></div>
              <div class="assignment-time"><span>{{ new Date(item.startAt).toLocaleString('zh-CN') }}</span><b>至</b><span>{{ new Date(item.dueAt).toLocaleString('zh-CN') }}</span></div>
              <div class="assignment-actions"><button type="button" class="secondary-button compact-button" @click="expandedAssignmentId = expandedAssignmentId === item.id ? '' : item.id">{{ expandedAssignmentId === item.id ? '收起分组' : '管理分组与共享' }}</button><button type="button" class="danger-button compact-button" :disabled="busy" :aria-label="`删除任务 ${item.title}`" @click="removeAssignment(item)">删除任务</button></div>
              <AssignmentGroups v-if="expandedAssignmentId === item.id" :assignment="item" @updated="loadData" />
            </article>
            <p v-if="!assignments.length" class="muted-copy">尚未发布实验任务。</p>
          </div>
        </div>
        <div class="work-panel panel-wide requirements-section">
          <div class="panel-heading"><p>30 天</p><h2>已删除任务 · 可恢复</h2></div>
          <div class="assignment-list">
            <article v-for="item in deletedAssignments" :key="item.id" class="deleted-assignment-row"><div><strong>{{ item.title }}</strong><span>{{ item.className }} · {{ item.templateName }} v{{ item.versionNumber }}</span><small>预计永久清理：{{ item.purgeAfter ? new Date(item.purgeAfter).toLocaleString('zh-CN') : '待确认' }}</small></div><button type="button" class="secondary-button compact-button" :disabled="busy" @click="restoreAssignment(item)">恢复任务与数据</button></article>
            <p v-if="!deletedAssignments.length" class="muted-copy">保留区暂无任务。</p>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.checkbox-label { display: flex; align-items: center; gap: 9px; }
.checkbox-label input { width: auto; min-height: 0; }
.assignment-list .assignment-with-groups { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: start; }
.assignment-with-groups :deep(.group-manager) { grid-column: 1 / -1; }
.assignment-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.assignment-actions button { margin: 0; }
.deleted-assignment-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.deleted-assignment-row small { display: block; margin-top: 5px; color: var(--muted); }
@media (max-width: 800px) { .assignment-list .assignment-with-groups { grid-template-columns: 1fr; } .assignment-time { text-align: left; } .deleted-assignment-row { align-items: flex-start; flex-direction: column; } }
</style>
