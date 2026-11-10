import { expect, test, type Page } from '@playwright/test'

const SUBMITTER_APP = 'http://localhost:5173'
const REVIEWER_APP = 'http://localhost:5174'

async function logout(page: Page) {
  await page.getByRole('banner').getByRole('button', { name: /Sam|Riya/ }).click()
  await page.getByRole('menuitem', { name: 'Log out' }).click()
}

async function login(page: Page, app: string, email: string, password: string) {
  await page.goto(`${app}/login`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).toHaveURL(`${app}/`)
}

test('submitter sees a reviewer rejection with its comment', async ({ page }) => {
  const title = `Expense report ${Date.now()}`
  const comment = 'Receipts are missing for the hotel stay.'

  await login(page, SUBMITTER_APP, 'sam.submitter@docflow.dev', 'submitter123')
  await page.getByLabel('Title').fill(title)
  await page.getByLabel('File').setInputFiles({ name: 'report.txt', mimeType: 'text/plain', buffer: Buffer.from('Q3 expenses') })
  await page.getByRole('button', { name: 'Submit' }).click()
  const samRow = page.getByRole('row').filter({ hasText: title })
  await expect(samRow.getByText('Pending')).toBeVisible()
  await logout(page)

  await login(page, REVIEWER_APP, 'riya.reviewer@docflow.dev', 'reviewer123')
  await page.getByRole('row').filter({ hasText: title }).getByRole('button', { name: 'Reject' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Comment').fill(comment)
  await dialog.getByRole('button', { name: 'Reject' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('row').filter({ hasText: title })).toBeHidden()
  await logout(page)

  await login(page, SUBMITTER_APP, 'sam.submitter@docflow.dev', 'submitter123')
  await expect(samRow.getByText('Rejected')).toBeVisible()
  await samRow.getByText('Rejected').hover()
  await expect(page.getByRole('tooltip')).toHaveText(comment)
})
