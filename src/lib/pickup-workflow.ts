import { PickupStatus } from '@prisma/client';

export const PICKUP_TRANSITIONS: Record<PickupStatus, PickupStatus[]> = {
  REQUESTED: ['ASSIGNED', 'CANCELLED'],
  ASSIGNED: ['ACCEPTED', 'RESCHEDULED', 'CANCELLED'],
  ACCEPTED: ['EN_ROUTE', 'RESCHEDULED', 'CANCELLED'],
  EN_ROUTE: ['ARRIVED', 'ISSUE_REPORTED', 'CANCELLED'],
  ARRIVED: ['COLLECTED', 'ISSUE_REPORTED', 'CANCELLED'],
  COLLECTED: ['DELIVERED', 'ISSUE_REPORTED'],
  DELIVERED: ['COMPLETED', 'ISSUE_REPORTED'],
  COMPLETED: [],
  RESCHEDULED: ['ASSIGNED', 'CANCELLED'],
  ISSUE_REPORTED: ['ASSIGNED', 'RESCHEDULED', 'CANCELLED'],
  CANCELLED: [],
};

export function canTransitionPickup(from: PickupStatus, to: PickupStatus) {
  return PICKUP_TRANSITIONS[from]?.includes(to) ?? false;
}

export function assertPickupTransition(from: PickupStatus, to: PickupStatus) {
  if (!canTransitionPickup(from, to)) {
    throw new Error(`Invalid pickup transition: ${from} -> ${to}`);
  }
}
