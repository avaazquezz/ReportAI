// What the API last said that the app needs to open and record with no coverage, kept on the
// device. Read only when the API can't be reached: the server still decides who is signed in, and
// nothing goes up without a valid token. Signing out, or the server ending the session, wipes it.
const PREFIX = 'reportai_offline:'

export function keepOfflineCopy(name: string, value: unknown) {
  if (import.meta.server) return
  localStorage.setItem(PREFIX + name, JSON.stringify(value))
}

export function readOfflineCopy<T>(name: string): T | null {
  if (import.meta.server) return null
  const stored = localStorage.getItem(PREFIX + name)
  return stored === null ? null : (JSON.parse(stored) as T)
}

export function forgetOfflineCopies() {
  if (import.meta.server) return
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith(PREFIX)) localStorage.removeItem(key)
  }
}
