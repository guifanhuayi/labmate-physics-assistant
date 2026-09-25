export type Values = Record<string, string>

export function mergeValues(base: Values, local: Values, remote: Values) {
  const merged: Values = {}
  const conflicts: string[] = []
  for (const key of new Set([...Object.keys(base), ...Object.keys(local), ...Object.keys(remote)])) {
    const original = base[key]
    const mine = local[key]
    const theirs = remote[key]
    const localChanged = mine !== original
    const remoteChanged = theirs !== original
    if (localChanged && remoteChanged && mine !== theirs) conflicts.push(key)
    const chosen = localChanged ? mine : theirs
    if (chosen !== undefined) merged[key] = chosen
  }
  return { merged, conflicts }
}
