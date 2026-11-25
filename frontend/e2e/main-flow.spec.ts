import { readFile } from 'node:fs/promises'
import { expect, test, type APIRequestContext } from '@playwright/test'

// The installation infra/e2e/seed.py sets up: its administrator, and the address the "Site visit
// report" type emails every report to.
const ADMIN = { email: 'admin@e2e.example.com', password: 'e2e-admin-password' }
const REPORT_RECIPIENT = 'office@e2e.example.com'
const MAILPIT = process.env.E2E_MAILPIT_URL ?? 'http://localhost:18025'

// Generous for a worker that answers in seconds, bounded so a stuck report fails the test.
const PIPELINE_TIMEOUT = 90_000

interface MailpitAddress { Address: string }
interface MailpitSummary { ID: string; To: MailpitAddress[] }
interface MailpitAttachment { PartID: string; FileName: string; ContentType: string }

function expectPdf(bytes: Buffer) {
  expect(bytes.length).toBeGreaterThan(0)
  expect(bytes.subarray(0, 5).toString('latin1')).toBe('%PDF-')
  expect(bytes.includes('%%EOF')).toBe(true) // not cut short
}

async function messageTo(request: APIRequestContext, address: string): Promise<MailpitSummary | undefined> {
  const response = await request.get(`${MAILPIT}/api/v1/messages`)
  expect(response.ok()).toBe(true)
  const { messages } = (await response.json()) as { messages: MailpitSummary[] }
  return messages.find((message) => message.To.some((to) => to.Address === address))
}

test.beforeEach(async ({ request }) => {
  // Only this run's email may count: an earlier run on the same stack sent an identical one.
  expect((await request.delete(`${MAILPIT}/api/v1/messages`)).ok()).toBe(true)
})

test('a typed note becomes a reviewed, corrected and delivered PDF', async ({ page, request }) => {
  // The AI stand-in (infra/e2e/ai_stub.py) fills the fields with fixed values and the findings with
  // the note itself: a note of this run's own proves it is the text that reached the model.
  const note = `Visited Acme Facilities at 12 Harbour Road with Jane Doe and Tom Lee for the quarterly fire safety walkthrough. Two extinguishers are out of date (run ${Date.now()}).`
  const client = () => page.getByLabel('Client', { exact: true })
  // The report's status is a chip without a role of its own; the history repeats the same words.
  const status = (label: string) => page.locator('.v-chip', { hasText: new RegExp(`^${label}$`) })

  await test.step('sign in', async () => {
    await page.goto('/login')
    await page.getByLabel('Email').fill(ADMIN.email)
    await page.getByLabel('Password').fill(ADMIN.password)
    await page.getByRole('button', { name: 'Log in', exact: true }).click()
    await expect(page).toHaveURL(/\/dashboard$/)
  })

  await test.step('capture a typed note', async () => {
    await page.goto('/capture')
    await expect(page.getByText('Report: Site visit report')).toBeVisible()
    await page.getByLabel('Or type the report').fill(note)
    await page.getByRole('button', { name: 'Send', exact: true }).click()
    await expect(page).toHaveURL(/\/admin\/reports\/[0-9a-f-]{36}$/)
  })

  await test.step('the extracted fields wait for review', async () => {
    // The page polls the report while the worker has it.
    await expect(status('Awaiting approval')).toBeVisible({ timeout: PIPELINE_TIMEOUT })
    await expect(client()).toHaveValue('Acme Facilities')
    await expect(page.getByLabel('Place', { exact: true })).toHaveValue('12 Harbour Road')
    await expect(page.getByLabel('Date', { exact: true })).toHaveValue('2026-11-20')
    await expect(page.getByLabel('Findings', { exact: true })).toHaveValue(note)
  })

  await test.step('correct a field and approve', async () => {
    await client().fill('Acme Facilities Ltd')
    await page.getByRole('button', { name: 'Approve with changes', exact: true }).click()
    await expect(status('Delivered')).toBeVisible({ timeout: PIPELINE_TIMEOUT })
    await expect(page.getByRole('row').filter({ hasText: REPORT_RECIPIENT })).toContainText('Sent')
  })

  await test.step('the correction is what was kept', async () => {
    await page.reload()
    await expect(client()).toHaveValue('Acme Facilities Ltd')
    await expect(page.getByText('Client: Acme Facilities → Acme Facilities Ltd')).toBeVisible()
  })

  await test.step('download the PDF', async () => {
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download PDF', exact: true }).click()
    expectPdf(await readFile(await (await download).path()))
  })

  await test.step('the PDF was emailed to the recipient', async () => {
    let message: MailpitSummary | undefined
    await expect
      .poll(async () => (message = await messageTo(request, REPORT_RECIPIENT)), { timeout: 30_000 })
      .toBeDefined()
    const detail = (await (await request.get(`${MAILPIT}/api/v1/message/${message!.ID}`)).json()) as {
      Attachments: MailpitAttachment[]
    }
    const pdfs = detail.Attachments.filter((attachment) => attachment.ContentType === 'application/pdf')
    expect(pdfs).toHaveLength(1)
    expect(pdfs[0]!.FileName).toMatch(/^Site visit report \d{4}-\d{2}-\d{2}\.pdf$/)
    const part = await request.get(`${MAILPIT}/api/v1/message/${message!.ID}/part/${pdfs[0]!.PartID}`)
    expect(part.ok()).toBe(true)
    expectPdf(await part.body())
  })
})
