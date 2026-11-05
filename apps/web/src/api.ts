import type { components } from './api.generated';

export type Case = components['schemas']['CaseView'];
export type CaseDetail = components['schemas']['CaseDetail'];
export type Run = components['schemas']['RunView'];
export type Operation = components['schemas']['OperationView'];
export type Snapshot = components['schemas']['SnapshotView'];
export type Capabilities = components['schemas']['CapabilityView'];
export type CaseCreate = components['schemas']['CaseCreate'];
export type Bundle = components['schemas']['BundleView'];

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = Array.isArray(body?.detail) ? body.detail.map((item: { msg: string }) => item.msg).join(' · ') : body?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Requête refusée (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const coverageLabel = (status: string) => ({
  partial: 'Couverture partielle', unsupported: 'Non pris en charge',
  unknown: 'Couverture inconnue', complete_within_declared_scope: 'Complet dans le périmètre déclaré',
}[status] ?? status);
