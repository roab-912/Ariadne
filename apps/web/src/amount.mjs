/** Mise en forme exacte par manipulation de chaînes ; aucun flottant. */
export function formatAmount(raw, decimals) {
  if (!/^(0|[1-9][0-9]*)$/.test(raw)) throw new Error('Montant brut invalide');
  if (decimals === null) return `${raw} unités brutes (décimales inconnues)`;
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 255) throw new Error('Décimales invalides');
  if (decimals === 0) return raw;
  const padded = raw.padStart(decimals + 1, '0');
  const fraction = padded.slice(-decimals).replace(/0+$/, '');
  return `${padded.slice(0, -decimals)}${fraction ? `,${fraction}` : ''}`;
}
