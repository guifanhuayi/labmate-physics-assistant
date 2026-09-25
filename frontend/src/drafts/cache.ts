import type { StudentAssignment, StudentAssignmentSummary } from '../api/stage4'

export interface CachedData {
  version: number
  baseValues: Record<string, string>
  values: Record<string, string>
  updatedAt: string
}

type CacheValue = StudentAssignment | StudentAssignmentSummary[] | CachedData

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const operation = indexedDB.open('labmate-stage4', 1)
    operation.onupgradeneeded = () => {
      if (!operation.result.objectStoreNames.contains('entries')) operation.result.createObjectStore('entries')
    }
    operation.onsuccess = () => resolve(operation.result)
    operation.onerror = () => reject(operation.error)
  })
}

export async function cacheRead<T extends CacheValue>(key: string): Promise<T | null> {
  const database = await openDatabase()
  try {
    return await new Promise<T | null>((resolve, reject) => {
      const transaction = database.transaction('entries', 'readonly')
      const operation = transaction.objectStore('entries').get(key)
      operation.onsuccess = () => resolve((operation.result as T | undefined) ?? null)
      operation.onerror = () => reject(operation.error)
    })
  } finally { database.close() }
}

export async function cacheWrite(key: string, value: CacheValue): Promise<void> {
  const database = await openDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction('entries', 'readwrite')
      // Vue's reactive proxies cannot be structured-cloned by IndexedDB.
      transaction.objectStore('entries').put(JSON.parse(JSON.stringify(value)), key)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error)
      transaction.onabort = () => reject(transaction.error)
    })
  } finally { database.close() }
}
