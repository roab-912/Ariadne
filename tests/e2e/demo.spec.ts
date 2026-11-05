import { test, expect } from '../../apps/web/node_modules/@playwright/test';

test('parcourt la démonstration, le montant exact et les pièces', async ({ page }, testInfo) => {
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('note')).toContainText('Démonstration');
  await expect(page.getByRole('heading', { name: 'Transfert puis dispersion' })).toBeVisible();
  await expect(page.getByText('1,000000000000000001 ETH', { exact: true })).toBeVisible();
  await expect(page.getByText('Aucune assertion', { exact: true })).toBeVisible();
  await expect(page.getByText('Aucune allocation', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Transfert · 100', exact: true }).click();
  await page.getByText('Contenu de la pièce synthétique', { exact: true }).click();
  await expect(page.getByLabel('Détails et preuves')).toContainText('1000000000000000001');
  await page.screenshot({ path: testInfo.outputPath('demo-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('heading', { name: 'Transfert puis dispersion' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath('demo-mobile.png'), fullPage: true });
  expect(pageErrors).toEqual([]);
});
