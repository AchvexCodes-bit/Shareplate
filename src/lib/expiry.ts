import { db } from '@/lib/db';

export async function expireListings(now = new Date()) {
  const listings = await db.foodListing.findMany({
    where: {
      availableUntil: { lte: now },
      status: { in: ['PUBLISHED', 'PARTIALLY_RESERVED', 'FULLY_RESERVED'] },
    },
    select: { id: true, status: true, organizationId: true, reference: true },
  });

  for (const listing of listings) {
    await db.$transaction(async (tx) => {
      const current = await tx.foodListing.findUnique({ where: { id: listing.id } });
      if (!current || !['PUBLISHED', 'PARTIALLY_RESERVED', 'FULLY_RESERVED'].includes(current.status)) return;

      await tx.foodListing.update({ where: { id: listing.id }, data: { status: 'EXPIRED' } });
      await tx.listingStatusHistory.create({
        data: { listingId: listing.id, fromStatus: current.status, toStatus: 'EXPIRED', reason: 'Availability window ended' },
      });

      const reservations = await tx.reservation.findMany({
        where: { listingId: listing.id, status: { in: ['REQUESTED', 'ACCEPTED'] } },
        select: { requestedById: true, reference: true },
      });
      if (reservations.length) {
        await tx.notification.createMany({
          data: reservations.map((r) => ({
            userId: r.requestedById,
            type: 'LISTING_EXPIRED',
            title: 'Listing expired',
            message: `Listing ${current.reference} is no longer available for new collection.`,
            relatedEntityType: 'LISTING',
            relatedEntityId: current.id,
          })),
        });
      }
    });
  }
  return listings.length;
}
