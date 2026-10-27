export type AdminSection = 'overview' | 'classes' | 'roster' | 'teachers'

export interface AdminProps {
  section: AdminSection
  user: { name: string; account: string }
  demoEnabled: boolean
  onNavigate: (section: AdminSection) => void
  onLogout: () => Promise<void>
}

export interface AdminMount {
  update: (props: AdminProps) => void
  unmount: () => void
}
