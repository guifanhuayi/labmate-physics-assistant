import { createRoot } from 'react-dom/client'
import { StyleProvider } from '@ant-design/cssinjs'
import '@ant-design/v5-patch-for-react-19'
import reset from 'antd/dist/reset.css?inline'
import adminStyles from './styles.css?inline'
import { AdminConsole } from './AdminConsole'
import type { AdminMount, AdminProps } from './types'

export function mountAdmin(host: HTMLElement, props: AdminProps): AdminMount {
  // Both component styles and popup containers stay within the admin route.
  const shadow = host.shadowRoot || host.attachShadow({ mode: 'open' })
  shadow.replaceChildren()
  const style = document.createElement('style')
  style.textContent = `${reset}\n${adminStyles}`
  const container = document.createElement('div')
  container.className = 'admin-pro-root'
  shadow.append(style, container)
  const root = createRoot(container)
  const update = (next: AdminProps) => root.render(
    <StyleProvider container={shadow}>
      <AdminConsole {...next} popupContainer={container} />
    </StyleProvider>,
  )
  update(props)
  return { update, unmount: () => { root.unmount(); shadow.replaceChildren() } }
}
