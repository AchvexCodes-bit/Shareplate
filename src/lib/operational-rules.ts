import { ListingStatus, ReservationStatus } from '@prisma/client';

export function listingRemaining(quantityListed: number, quantityReserved: number, quantityCollected: number) {
  return Math.max(0, quantityListed - quantityReserved - quantityCollected);
}

export function canReserve(status: ListingStatus, availableUntil: Date, quantity: number, listed: number, reserved: number, collected: number, organizationVerified: boolean) {
  if (!organizationVerified) return { ok: false, reason: 'Your organization must be verified before making reservations.' };
  if (availableUntil.getTime() <= Date.now()) return { ok: false, reason: 'This listing is no longer available for reservation.' };
  if (!['PUBLISHED', 'PARTIALLY_RESERVED'].includes(status)) return { ok: false, reason: 'This listing is not accepting reservations.' };
  if (!Number.isInteger(quantity) || quantity <= 0) return { ok: false, reason: 'Enter a valid quantity.' };
  const remaining = listingRemaining(listed, reserved, collected);
  if (quantity > remaining) return { ok: false, reason: `Only ${remaining} units remain available.` };
  return { ok: true as const };
}

export const TERMINAL_RESERVATION_STATUSES: ReservationStatus[] = ['COMPLETED', 'CANCELLED', 'REJECTED'];
