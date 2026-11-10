// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { demoLimitHit, demoRows } from '../app/utils/demoFields.ts'

const es = { locale: 'es', yes: 'Sí', no: 'No' }
const en = { locale: 'en', yes: 'Yes', no: 'No' }

test("rows follow the schema's order, with its labels or a readable name", () => {
  const rows = demoRows(
    { obra: { type: 'str', label: 'Obra' }, fecha_visita: { type: 'date' } },
    { obra: 'Calle Mayor, 12', fecha_visita: '2026-11-09' },
    [],
    es
  )
  assert.deepEqual(
    rows.map((row) => [row.key, row.label, row.value]),
    [
      ['obra', 'Obra', 'Calle Mayor, 12'],
      ['fecha_visita', 'Fecha visita', '09/11/2026']
    ]
  )
})

test('what was not said stays empty, and a required one is flagged missing', () => {
  const rows = demoRows(
    { plazo: { type: 'str', required: true }, notas: { type: 'str', required: false } },
    { plazo: '   ', notas: null },
    ['plazo'],
    es
  )
  assert.deepEqual(rows.map((row) => [row.value, row.missing]), [[null, true], [null, false]])
})

test('tables and lists print one line per row or item; photo fields are left out', () => {
  const rows = demoRows(
    {
      deficiencias: { type: 'list[object]' },
      empresas: { type: 'list[str]' },
      fotos: { type: 'image' },
      paralizacion: { type: 'bool' }
    },
    {
      deficiencias: [
        { deficiencia: 'Falta barandilla', empresa: 'Estructuras Levante', plazo: '' },
        { deficiencia: 'Sin red', empresa: 'Montajes Soler', plazo: 'Hoy' }
      ],
      empresas: ['Albufera', 'Soler'],
      paralizacion: false
    },
    [],
    es
  )
  assert.deepEqual(rows.map((row) => row.value), [
    'Falta barandilla · Estructuras Levante\nSin red · Montajes Soler · Hoy',
    'Albufera\nSoler',
    'No'
  ])
})

test("a table's cells follow the template's columns whatever order the model wrote, an empty one as a dash", () => {
  const columns = {
    deficiencia: { type: 'str' },
    empresa: { type: 'str' },
    medida: { type: 'str' },
    plazo: { type: 'date' }
  }
  const rows = demoRows(
    { deficiencias: { type: 'list[object]', columns } },
    {
      deficiencias: [
        { plazo: '2026-11-10', medida: 'Colocar la barandilla', empresa: 'Construcciones Ibarra', deficiencia: 'Falta la barandilla' },
        { medida: 'Tapar el cuadro', empresa: 'Ferralla Norte', deficiencia: 'Cuadro sin tapa', plazo: null },
        { deficiencia: '', empresa: null }
      ]
    },
    [],
    es
  )
  assert.equal(
    rows[0]!.value,
    'Falta la barandilla · Construcciones Ibarra · Colocar la barandilla · 10/11/2026\nCuadro sin tapa · Ferralla Norte · Tapar el cuadro · —'
  )
})

test('dates and decimals are written as the report writes them in each language', () => {
  const schema = { fecha: { type: 'date' }, hora: { type: 'time' }, altura: { type: 'float' } }
  const fields = { fecha: '2026-11-09', hora: '09:30:00', altura: 2.5 }
  assert.deepEqual(demoRows(schema, fields, [], es).map((row) => row.value), ['09/11/2026', '09:30', '2,5'])
  assert.deepEqual(demoRows(schema, fields, [], en).map((row) => row.value), ['2026-11-09', '09:30', '2.5'])
})

test('a date the model did not write as ISO is shown as it came', () => {
  assert.equal(demoRows({ plazo: { type: 'date' } }, { plazo: 'mañana' }, [], es)[0]!.value, 'mañana')
})

test('no schema yet, no rows', () => {
  assert.deepEqual(demoRows(null, null, [], es), [])
})

test("the two daily limits read apart, though both say 'today'", () => {
  assert.equal(demoLimitHit('You have used your demo tries for today.'), 'perIp')
  assert.equal(demoLimitHit('The demo is full for today. Try again tomorrow.'), 'full')
  assert.equal(demoLimitHit(undefined), 'perIp')
})
