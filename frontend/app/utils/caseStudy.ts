// The case study (pages/arquitectura.vue) is a drawing set: sheets in reading order, each at its
// own scale. One list, so the cover's index, every title block and the header's nav agree.

export const SHEETS = ['system', 'server', 'agent', 'tenancy', 'fieldApp', 'quality', 'revisions'] as const
export type SheetKey = (typeof SHEETS)[number]

/** The anchor of each sheet: the header, the index and the system map's detail marks link here. */
export const SHEET_IDS: Record<SheetKey, string> = {
  system: 'sistema',
  server: 'servidor',
  agent: 'agente',
  tenancy: 'empresas',
  fieldApp: 'app-de-campo',
  quality: 'calidad',
  revisions: 'revisiones'
}

export const sheetNumber = (sheet: SheetKey) => SHEETS.indexOf(sheet) + 1
