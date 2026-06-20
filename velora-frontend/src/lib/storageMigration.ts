const STORAGE_KEY_PREFIX = "sorimemo_"
const LEGACY_STORAGE_KEY_PREFIX = "velora_"

function migrateStorage(storage: Storage) {
  const pending: Array<[string, string]> = []
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index)
    if (!key?.startsWith(LEGACY_STORAGE_KEY_PREFIX)) continue
    const nextKey = `${STORAGE_KEY_PREFIX}${key.slice(LEGACY_STORAGE_KEY_PREFIX.length)}`
    if (storage.getItem(nextKey) === null) {
      const value = storage.getItem(key)
      if (value !== null) pending.push([nextKey, value])
    }
  }
  pending.forEach(([key, value]) => storage.setItem(key, value))
}

export function migrateSoriMemoStorage() {
  migrateStorage(localStorage)
  migrateStorage(sessionStorage)
}
