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

test('crée une adresse bornée et affiche le fournisseur absent sans données simulées', async ({ page, request }) => {
  const capabilities = await (await request.get('/api/v1/capabilities')).json();
  test.skip(capabilities.providers.some((provider: { transaction_bundle: boolean }) => provider.transaction_bundle),
    'Ce contrôle cible explicitement une instance sans fournisseur RPC configuré');
  const title = `Vérification interface V0.2 ${Date.now()}`;
  await page.goto('/');
  await page.getByRole('button', { name: '+ Nouveau dossier' }).click();
  await page.getByLabel('Titre', { exact: true }).fill(title);
  await page.getByLabel('Type de graine').selectOption('address');
  await page.getByLabel('Adresse', { exact: true }).fill('0x1111111111111111111111111111111111111111');
  await page.getByLabel('Bloc de début').fill('26347604');
  await page.getByLabel('Bloc de fin').fill('26347604');
  await page.getByRole('button', { name: 'Enregistrer le dossier' }).click();
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
  await expect(page.getByRole('note')).toContainText('Collecte Ethereum');
  await page.getByRole('button', { name: 'Collecter Ethereum', exact: true }).click();
  await expect(page.getByText('Non pris en charge', { exact: true })).toBeVisible();
  await expect(page.getByText('Collecte indisponible pour ce run.', { exact: false })).toBeVisible();
  await expect(page.getByText('rpc_not_configured', { exact: true })).toBeVisible();
  await expect(page.getByText('0 mouvements affichés', { exact: true })).toBeVisible();
  await expect(page.getByRole('note')).not.toContainText('Démonstration');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
