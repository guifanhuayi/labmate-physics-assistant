<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError, managementApi, type AssignmentView, type StudentView } from '../api/client'
import { stage4Api, type ExperimentGroup } from '../api/stage4'

const props = defineProps<{ assignment: AssignmentView }>()
const emit = defineEmits<{ updated: [] }>()
const students = ref<StudentView[]>([])
const groups = ref<ExperimentGroup[]>([])
const groupName = ref('')
const selected = ref<string[]>([])
const editingGroup = ref('')
const busy = ref(false)
const error = ref('')
const message = ref('')

async function load() {
  try {
    [students.value, groups.value] = await Promise.all([
      managementApi.listClassStudents(props.assignment.classId),
      stage4Api.groups(props.assignment.id),
    ])
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '无法读取小组信息。' }
}

function showError(cause: unknown) {
  error.value = cause instanceof ApiError ? cause.message : '操作失败，请稍后重试。'
  message.value = ''
}

async function toggleSharing() {
  busy.value = true; error.value = ''; message.value = ''
  try {
    await stage4Api.setSharing(props.assignment.id, !props.assignment.groupSharingEnabled)
    message.value = props.assignment.groupSharingEnabled ? '已关闭本实验组内共享。' : '已开启本实验组内共享。'
    emit('updated')
  } catch (cause) { showError(cause) } finally { busy.value = false }
}

async function saveGroup() {
  busy.value = true; error.value = ''; message.value = ''
  try {
    if (editingGroup.value) {
      await stage4Api.setMembers(props.assignment.id, editingGroup.value, selected.value)
      message.value = '小组成员已更新并记录审计。'
    } else {
      await stage4Api.createGroup(props.assignment.id, groupName.value.trim(), selected.value)
      message.value = '实验小组已创建。'
    }
    groupName.value = ''; selected.value = []; editingGroup.value = ''
    await load()
  } catch (cause) { showError(cause) } finally { busy.value = false }
}

function edit(group: ExperimentGroup) {
  editingGroup.value = group.id
  groupName.value = group.name
  selected.value = [...group.memberIds]
}

onMounted(load)
</script>

<template>
  <div class="group-manager">
    <p class="field-help">共享须同时满足：本任务已开启、对应测量数据设为“组内共享”、学生属于本实验小组。教师不能修改学生录入的数据。</p>
    <button type="button" class="secondary-button compact-button" :disabled="busy" @click="toggleSharing">{{ assignment.groupSharingEnabled ? '关闭组内共享' : '开启组内共享' }}</button>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p v-if="message" class="success-message" role="status">{{ message }}</p>
    <div v-for="group in groups" :key="group.id" class="group-row">
      <div><strong>{{ group.name }}</strong><small>{{ group.members.length ? group.members.map((member) => `${member.name}（${member.studentNumber}）`).join('、') : '尚无组员' }}</small></div>
      <button type="button" class="secondary-button compact-button" @click="edit(group)">编辑成员</button>
    </div>
    <form class="group-form" @submit.prevent="saveGroup">
      <h3>{{ editingGroup ? `调整 ${groupName} 的成员` : '创建实验小组' }}</h3>
      <label v-if="!editingGroup" for="group-name">小组名称</label><input v-if="!editingGroup" id="group-name" v-model="groupName" required maxlength="80" />
      <fieldset><legend>从本班选择组员</legend>
        <label v-for="student in students" :key="student.id" class="group-student"><input v-model="selected" type="checkbox" :value="student.id" />{{ student.name }} · {{ student.studentNumber }}</label>
      </fieldset>
      <div class="group-actions"><button type="submit" class="primary-button" :disabled="busy || (!editingGroup && !groupName.trim())">{{ editingGroup ? '保存成员' : '创建小组' }}</button><button v-if="editingGroup" type="button" class="secondary-button" @click="editingGroup = ''; groupName = ''; selected = []">取消编辑</button></div>
    </form>
  </div>
</template>

<style scoped>
.group-manager { padding-top: 14px; border-top: 1px solid #d9e3e3; }
.group-row { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 12px 0; border-bottom: 1px solid #e4ecec; }
.group-row small { display: block; color: #5f7070; margin-top: 4px; }
.group-form { display: grid; gap: 10px; margin-top: 18px; }
.group-form fieldset { display: flex; flex-wrap: wrap; gap: 12px; border: 1px solid #d9e3e3; border-radius: 10px; padding: 12px; max-height: 220px; overflow: auto; }
.group-student { display: inline-flex; align-items: center; gap: 5px; margin: 0; }
.group-student input { min-height: 0; width: auto; }
.group-actions { display: flex; gap: 10px; }
@media (max-width: 680px) { .group-row { align-items: flex-start; flex-direction: column; } }
</style>
