import { useEffect, useRef, useState } from 'react'
import { PageContainer, ProForm, ProFormSelect, ProFormText, ProLayout, ProTable, type ProColumns } from '@ant-design/pro-components'
import { Alert, Button, Card, ConfigProvider, Drawer, Input, Modal, Select, Space, Statistic, Tag, Typography, Upload } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { ApiError, managementApi, type ClassView, type ImportPreview, type StudentView, type TeacherView } from '../api/client'
import type { AdminProps, AdminSection } from './types'

const navigation: Array<{ path: string; name: string; section: AdminSection }> = [
  { path: '/admin/overview', name: '工作概览', section: 'overview' },
  { path: '/admin/classes', name: '班级管理', section: 'classes' },
  { path: '/admin/roster', name: '名单导入', section: 'roster' },
  { path: '/admin/teachers', name: '教师目录', section: 'teachers' },
]
function errorText(error: unknown) { return error instanceof ApiError ? error.message : '暂时无法完成操作，请重试。' }

interface ConsoleProps extends AdminProps { popupContainer: HTMLElement }

export function AdminConsole(props: ConsoleProps) {
  const [classes, setClasses] = useState<ClassView[]>([])
  const [teachers, setTeachers] = useState<TeacherView[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [createError, setCreateError] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<ClassView | null>(null)
  const [selectedClass, setSelectedClass] = useState<ClassView | null>(null)
  const [students, setStudents] = useState<StudentView[]>([])
  const [studentsLoading, setStudentsLoading] = useState(false)
  const [studentsError, setStudentsError] = useState('')
  const [studentsRevision, setStudentsRevision] = useState(0)
  const [keyword, setKeyword] = useState('')
  const [teacherFilter, setTeacherFilter] = useState<string | undefined>()
  const live = useRef(true)

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [nextClasses, nextTeachers] = await Promise.all([managementApi.listClasses(), managementApi.listTeachers()])
      if (!live.current) return
      setClasses(nextClasses)
      setTeachers(nextTeachers)
      setStudentsRevision(value => value + 1)
    } catch (cause) { if (live.current) setError(errorText(cause)) }
    finally { if (live.current) setLoading(false) }
  }
  useEffect(() => {
    live.current = true
    void loadData()
    return () => { live.current = false }
  }, [])
  useEffect(() => {
    let cancelled = false
    setStudents([])
    setStudentsError('')
    if (!selectedClass) return
    setStudentsLoading(true)
    managementApi.listClassStudents(selectedClass.id)
      .then(rows => { if (!cancelled) setStudents(rows) })
      .catch(cause => { if (!cancelled) setStudentsError(errorText(cause)) })
      .finally(() => { if (!cancelled) setStudentsLoading(false) })
    return () => { cancelled = true }
  }, [selectedClass?.id, studentsRevision])

  async function createClass(values: Record<string, string>) {
    setBusy(true); setError(''); setMessage(''); setCreateError('')
    try {
      await managementApi.createClass({ classCode: values.classCode, className: values.className, semester: values.semester, teacherId: values.teacherId })
      setMessage('班级已创建。')
      setCreateOpen(false)
      await loadData()
      return true
    } catch (cause) { setCreateError(errorText(cause)); return false }
    finally { setBusy(false) }
  }
  function openCreate() { setCreateError(''); setCreateOpen(true) }
  async function removeClass() {
    if (!deleteTarget) return
    setBusy(true); setError(''); setMessage('')
    try {
      await managementApi.deleteClass(deleteTarget.id)
      setMessage(`班级“${deleteTarget.className}”已删除，学生账号已保留。`)
      if (selectedClass?.id === deleteTarget.id) setSelectedClass(null)
      setDeleteTarget(null)
      await loadData()
    } catch (cause) { setError(errorText(cause)) }
    finally { setBusy(false) }
  }
  const classColumns: ProColumns<ClassView>[] = [
    { title: '班级代码', dataIndex: 'classCode', width: 135, sorter: (a, b) => a.classCode.localeCompare(b.classCode) },
    { title: '班级名称', dataIndex: 'className', ellipsis: true },
    { title: '学期', dataIndex: 'semester', width: 110 },
    { title: '负责教师', dataIndex: 'teacherName', width: 120 },
    { title: '学生人数', dataIndex: 'studentCount', width: 100, sorter: (a, b) => a.studentCount - b.studentCount },
    { title: '操作', valueType: 'option', width: 180, render: (_, item) => [
      <Button key="students" type="link" aria-label={`查看学生 ${item.classCode}`} onClick={() => setSelectedClass(item)}>查看学生</Button>,
      <Button key="delete" type="link" danger disabled={busy} aria-label={`删除班级 ${item.classCode}`} onClick={() => { setError(''); setDeleteTarget(item) }}>删除</Button>,
    ] },
  ]
  const studentColumns: ProColumns<StudentView>[] = [
    { title: '姓名', dataIndex: 'name' },
    { title: '学号', dataIndex: 'studentNumber' },
    { title: '首次设置', dataIndex: 'enrollmentCompleted', hideInTable: props.demoEnabled,
      render: (_, item) => <Tag color={item.enrollmentCompleted ? 'success' : 'warning'}>{item.enrollmentCompleted ? '已完成' : '待完成'}</Tag> },
  ]
  const teacherColumns: ProColumns<TeacherView>[] = [
    { title: '教师姓名', dataIndex: 'name' }, { title: '教师工号', dataIndex: 'account', copyable: true },
    { title: '负责班级', key: 'classes', render: (_, item) => classes.filter(row => row.teacherId === item.id).length },
  ]
  const filteredClasses = classes.filter(item => (!teacherFilter || item.teacherId === teacherFilter)
    && `${item.classCode} ${item.className}`.toLowerCase().includes(keyword.trim().toLowerCase()))
  const popup = () => props.popupContainer

  return <ConfigProvider locale={zhCN} getPopupContainer={popup} theme={{ token: {
    colorPrimary: '#1677ff', borderRadius: 6, fontSize: 14, colorBgLayout: '#f5f7fa',
  } }}>
    <ProLayout title="LabMate 管理" logo="/favicon.svg" layout="mix" navTheme="light" bgLayoutImgList={[]}
      siderWidth={224} fixSiderbar fixedHeader location={{ pathname: `/admin/${props.section}` }}
      route={{ path: '/admin', routes: navigation }}
      menuItemRender={(item, dom) => <button type="button" className="admin-menu-link"
        aria-current={item.path === `/admin/${props.section}` ? 'page' : undefined}
        onClick={() => props.onNavigate(navigation.find(row => row.path === item.path)?.section || 'overview')}>{dom}</button>}
      actionsRender={() => [
        <Tag key="role" color="blue">管理员</Tag>,
        <span key="name">{props.user.name} · {props.user.account}</span>,
        <Button key="logout" onClick={async () => { try { await props.onLogout() } catch (cause) { setError(errorText(cause)) } }}>退出登录</Button>,
      ]}
      footerRender={() => <footer className="admin-footer">LabMate · 物理实验教学管理</footer>}>
      <PageContainer title={navigation.find(item => item.section === props.section)?.name}
        content="管理班级、师生名单与教师信息。" extra={<Button loading={loading} onClick={() => void loadData()}>刷新数据</Button>}>
        {error && !deleteTarget && <Alert className="admin-feedback" role="alert" type="error" showIcon message={error} closable onClose={() => setError('')} />}
        {message && <div className="admin-feedback" role="status"><Alert type="success" showIcon message={message} closable onClose={() => setMessage('')} /></div>}
        {props.section === 'overview' && <>
          <div className="admin-metrics">
            <Card><Statistic title="班级总数" value={classes.length} loading={loading} suffix="个" /></Card>
            <Card><Statistic title="教师总数" value={teachers.length} loading={loading} suffix="位" /></Card>
            <Card><Statistic title="班级学生人次" value={classes.reduce((total, item) => total + item.studentCount, 0)} loading={loading} suffix="人次" /></Card>
          </div>
          <Card title="常用操作">
            <Typography.Paragraph>先为负责教师创建班级，再选择班级预览并导入学生名单。</Typography.Paragraph>
            <Space wrap>
              <Button type="primary" onClick={openCreate}>创建班级</Button>
              <Button onClick={() => props.onNavigate('roster')}>导入学生名单</Button>
              <Button onClick={() => props.onNavigate('classes')}>查看班级</Button>
            </Space>
          </Card>
        </>}
        {props.section === 'classes' && <ProTable<ClassView> headerTitle="班级列表" rowKey="id" search={false}
          loading={loading} columns={classColumns} dataSource={filteredClasses} scroll={{ x: 820 }}
          pagination={{ defaultPageSize: 10, showSizeChanger: true }} options={{ density: true, fullScreen: false, reload: () => void loadData() }}
          toolBarRender={() => [
            <Input.Search key="search" aria-label="搜索班级" placeholder="班级代码或名称" allowClear value={keyword} onChange={event => setKeyword(event.target.value)} style={{ width: 200 }} />,
            <Select key="teacher" aria-label="筛选负责教师" placeholder="全部教师" allowClear value={teacherFilter} onChange={setTeacherFilter}
              style={{ width: 150 }} options={teachers.map(item => ({ label: item.name, value: item.id }))} />,
            <Button key="create" type="primary" onClick={openCreate}>创建班级</Button>,
          ]} />}
        {props.section === 'roster' && <RosterPanel classes={classes} loading={loading} demoEnabled={props.demoEnabled}
          onImported={async text => { setMessage(text); await loadData() }} onError={setError} />}
        {props.section === 'teachers' && <ProTable<TeacherView> rowKey="id" headerTitle="教师目录" search={false} loading={loading}
          columns={teacherColumns} dataSource={teachers} pagination={{ defaultPageSize: 10 }} options={false} />}
      </PageContainer>
    </ProLayout>
    <Modal title="创建班级" open={createOpen} onCancel={() => { if (!busy) setCreateOpen(false) }} footer={null}
      getContainer={popup} destroyOnClose maskClosable={!busy} closable={!busy}>
      {createError && <Alert role="alert" type="error" showIcon message={createError} />}
      <ProForm onFinish={createClass} initialValues={{ semester: '2026秋' }} disabled={busy}
        submitter={{ searchConfig: { submitText: '确认创建', resetText: '重置' }, submitButtonProps: { loading: busy } }}>
        <ProFormText name="classCode" label="班级代码" placeholder="例如 PHY2401" rules={[{ required: true, whitespace: true, message: '请填写班级代码' }]} />
        <ProFormText name="className" label="班级名称" placeholder="例如 物理2401" rules={[{ required: true, whitespace: true, message: '请填写班级名称' }]} />
        <ProFormText name="semester" label="学期" rules={[{ required: true, whitespace: true, message: '请填写学期' }]} />
        <ProFormSelect name="teacherId" label="负责教师" placeholder="请选择教师" rules={[{ required: true, message: '请选择负责教师' }]}
          options={teachers.map(item => ({ label: `${item.name} · ${item.account}`, value: item.id }))} />
      </ProForm>
    </Modal>
    <Modal title="删除班级" open={!!deleteTarget} onCancel={() => { if (!busy) setDeleteTarget(null) }} onOk={() => void removeClass()}
      okText="确认删除" cancelText="取消" okButtonProps={{ danger: true }} confirmLoading={busy} getContainer={popup} maskClosable={!busy} closable={!busy}>
      {error && <Alert role="alert" type="error" showIcon message={error} />}
      <p>确认删除“{deleteTarget?.classCode} · {deleteTarget?.className}”？</p>
      <p>将删除班级成员关系和名单预览，学生账号会保留。已有实验任务的班级不能删除。</p>
    </Modal>
    <Drawer title={selectedClass ? `${selectedClass.className} · 学生名单` : '学生名单'} open={!!selectedClass} width={640}
      onClose={() => setSelectedClass(null)} getContainer={popup}>
      {studentsError ? <Alert role="alert" type="error" message={studentsError} action={<Button onClick={() => setStudentsRevision(value => value + 1)}>重试</Button>} />
        : <ProTable<StudentView> rowKey="id" columns={studentColumns} dataSource={students} loading={studentsLoading} search={false}
          pagination={{ defaultPageSize: 10 }} options={false} scroll={{ x: 420 }} />}
    </Drawer>
  </ConfigProvider>
}

interface RosterProps {
  classes: ClassView[]
  loading: boolean
  demoEnabled: boolean
  onImported: (message: string) => Promise<void>
  onError: (message: string) => void
}

function RosterPanel(props: RosterProps) {
  const [classId, setClassId] = useState(props.classes[0]?.id || '')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  useEffect(() => {
    if (!props.classes.some(item => item.id === classId)) {
      setClassId(props.classes[0]?.id || '')
      setPreview(null)
      generation.current++
    }
  }, [props.classes, classId])
  async function previewRoster() {
    if (!classId || !file) { props.onError('请选择班级和名单文件。'); return false }
    const current = ++generation.current
    setBusy(true); setPreview(null); props.onError('')
    try {
      const result = await managementApi.previewRoster(classId, file)
      if (current === generation.current) setPreview(result)
      return true
    } catch (cause) { props.onError(errorText(cause)); return false }
    finally { setBusy(false) }
  }
  async function commitRoster() {
    if (!preview || preview.errorCount) return
    setBusy(true); props.onError('')
    try {
      const result = await managementApi.commitRoster(preview.id)
      setPreview(null)
      await props.onImported(props.demoEnabled
        ? `导入完成：新增 ${result.created} 人，新增班级关系 ${result.membershipsAdded} 条。学生可用已导入的学号和任意非空密码演示登录。`
        : `导入完成：新增 ${result.created} 人，新增班级关系 ${result.membershipsAdded} 条；${result.requiresEnrollment} 名学生需用姓名和学号完成首次设置。`)
    } catch (cause) { props.onError(errorText(cause)) }
    finally { setBusy(false) }
  }
  return <Card title="名单预览与导入" className="admin-roster">
    <Alert type="info" showIcon message="名单只需要“学号、姓名”两列，班级由下方选择决定；旧文件中的班级列会被忽略。" />
    <ProForm onFinish={previewRoster} submitter={{ resetButtonProps: false,
      searchConfig: { submitText: '先预览' }, submitButtonProps: { loading: busy, disabled: props.loading } }}>
      <ProForm.Item label="目标班级" required>
        <Select aria-label="目标班级" value={classId || undefined} disabled={busy || props.loading} placeholder="请选择班级"
          options={props.classes.map(item => ({ value: item.id, label: `${item.classCode} · ${item.className}` }))}
          onChange={value => { setClassId(value); setPreview(null); generation.current++ }} />
      </ProForm.Item>
      <ProForm.Item label="Excel / CSV 名单" required>
        <Upload accept=".xlsx,.csv" maxCount={1} disabled={busy}
          fileList={file ? [{ uid: 'roster', name: file.name, status: 'done' }] : []}
          beforeUpload={next => { setFile(next); setPreview(null); generation.current++; return false }}
          onRemove={() => { setFile(null); setPreview(null); generation.current++; return true }}>
          <Button disabled={busy}>选择名单文件</Button>
        </Upload>
      </ProForm.Item>
    </ProForm>
    {preview && <div className="admin-preview">
      <Alert type={preview.errorCount ? 'warning' : 'success'} showIcon
        message={`有效 ${preview.validCount} 行 · 错误 ${preview.errorCount} 项`}
        description={preview.errorCount ? '请修正以下问题后重新预览。' : '预览通过，确认后将导入所选班级。'} />
      {preview.errors.length > 0 && <ul>{preview.errors.map((issue, index) => <li key={`${issue.row}-${issue.field}-${index}`}>第 {issue.row} 行：{issue.message}</li>)}</ul>}
      {!preview.errorCount && <Button className="admin-preview" type="primary" loading={busy} onClick={() => void commitRoster()}>确认导入</Button>}
    </div>}
  </Card>
}
