import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { requireUser } from '@/lib/guards';
import { assertPickupTransition } from '@/lib/pickup-workflow';
import { PickupStatus, Role } from '@prisma/client';

export async function GET() {
  try {
    const { user, role, organizationId } = await requireUser([Role.COURIER, Role.FOOD_PARTNER, Role.RECIPIENT_ORGANIZATION, Role.ADMIN]);
    const where = role === Role.COURIER ? { assignments: { some: { courier: { userId: user.id } } } } : role === Role.ADMIN ? {} : { OR: [{ sourceOrganizationId: organizationId }, { destinationOrganizationId: organizationId }] };
    const data = await db.pickupRequest.findMany({ where, include: { reservation: { include: { listing: { include: { category: true } } } }, sourceOrganization: { include: { addresses: true } }, destinationOrganization: { include: { addresses: true } }, assignments: { include: { courier: { include: { user: true } } } }, statusHistory: { orderBy: { createdAt: 'asc' } }, delivery: true }, orderBy: { windowStart: 'asc' }, take: 100 });
    return NextResponse.json({ data });
  } catch (e) { const status = e instanceof Error && e.message === 'UNAUTHENTICATED' ? 401 : 403; return NextResponse.json({ error: 'You do not have access to these pickups.' }, { status }); }
}

export async function PATCH(req: Request) {
  try {
    const { user, role } = await requireUser([Role.COURIER, Role.FOOD_PARTNER, Role.RECIPIENT_ORGANIZATION, Role.ADMIN]);
    const body = await req.json();
    const id = String(body.id || '');
    const to = String(body.status || '') as PickupStatus;
    const pickup = await db.pickupRequest.findUnique({ where: { id }, include: { assignments: { include: { courier: true } }, reservation: true } });
    if (!pickup) return NextResponse.json({ error: 'Pickup not found.' }, { status: 404 });
    if (role === Role.COURIER && !pickup.assignments.some(a => a.courier.userId === user.id)) return NextResponse.json({ error: 'This pickup is not assigned to you.' }, { status: 403 });
    assertPickupTransition(pickup.status, to);
    const now = new Date();
    const extra: Record<string, unknown> = {};
    if (to === 'ACCEPTED') extra.acceptedAt = now;
    if (to === 'COLLECTED') { const qty = Number(body.collectedQuantity); if (!Number.isInteger(qty) || qty <= 0) return NextResponse.json({ error: 'Enter the actual collected quantity.' }, { status: 400 }); extra.collectedQuantity = qty; extra.collectionAt = now; extra.collectionNotes = body.notes ? String(body.notes) : null; extra.collectionPhotoUrl = body.photoUrl ? String(body.photoUrl) : null; }
    if (to === 'DELIVERED') { if (pickup.status !== 'COLLECTED') return NextResponse.json({ error: 'Food must be collected before it can be delivered.' }, { status: 409 }); extra.deliveredQuantity = Number(body.receivedQuantity ?? pickup.collectedQuantity ?? 0); extra.deliveryAt = now; extra.deliveryCondition = body.condition || 'GOOD'; extra.deliveryPhotoUrl = body.photoUrl ? String(body.photoUrl) : null; }
    if (to === 'COMPLETED') { if (pickup.status !== 'DELIVERED') return NextResponse.json({ error: 'Delivery must be confirmed before completion.' }, { status: 409 }); }
    const updated = await db.$transaction(async tx => {
      const result = await tx.pickupRequest.update({ where: { id }, data: { status: to, ...extra } });
      await tx.pickupStatusHistory.create({ data: { pickupId: id, fromStatus: pickup.status, toStatus: to, changedByUserId: user.id, note: body.note ? String(body.note) : undefined } });
      if (to === 'COLLECTED') await tx.reservation.update({ where: { id: pickup.reservationId }, data: { status: 'COLLECTED' } });
      if (to === 'DELIVERED') {
        await tx.deliveryConfirmation.upsert({ where: { pickupId: id }, update: { deliveredAt: now, receivedQuantity: Number(body.receivedQuantity ?? pickup.collectedQuantity ?? 0), condition: body.condition || 'GOOD', notes: body.notes ? String(body.notes) : null, proofPhotoUrl: body.photoUrl ? String(body.photoUrl) : null }, create: { pickupId: id, collectedAt: pickup.collectionAt, deliveredAt: now, receivedQuantity: Number(body.receivedQuantity ?? pickup.collectedQuantity ?? 0), condition: body.condition || 'GOOD', notes: body.notes ? String(body.notes) : null, proofPhotoUrl: body.photoUrl ? String(body.photoUrl) : null } });
      }
      if (to === 'COMPLETED') {
        const received = pickup.deliveredQuantity ?? pickup.collectedQuantity ?? 0;
        await tx.reservation.update({ where: { id: pickup.reservationId }, data: { status: 'COMPLETED' } });
        await tx.impactRecord.upsert({ where: { pickupId: id }, update: { portions: received, reservationId: pickup.reservationId }, create: { pickupId: id, reservationId: pickup.reservationId, portions: received } });
      }
      await tx.auditLog.create({ data: { userId: user.id, action: 'PICKUP_STATUS_CHANGED', entityType: 'PICKUP', entityId: id, details: { from: pickup.status, to } } });
      return result;
    });
    return NextResponse.json({ data: updated });
  } catch (e) { const message = e instanceof Error ? e.message : 'We could not update this pickup.'; return NextResponse.json({ error: message.includes('Invalid pickup') ? message : 'We could not update this pickup.' }, { status: 400 }); }
}
