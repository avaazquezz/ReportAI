export const CHANNEL_NAMES: Record<string, string> = { telegram: 'Telegram', whatsapp: 'WhatsApp', email: 'Email', web: 'App' }

export function channelName(type: string): string {
  return CHANNEL_NAMES[type] ?? type
}
