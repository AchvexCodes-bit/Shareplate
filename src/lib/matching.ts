import { db } from '@/lib/db';

type MatchInput = { listingId: string; recipientOrganizationId?: string };

export async function getRecipientMatches({ listingId }: MatchInput) {
  const listing = await db.foodListing.findUnique({
    where: { id: listingId },
    include: { category: true, organization: { include: { addresses: { where: { isPrimary: true }, take: 1 } } } },
  });
  if (!listing) throw new Error('Listing not found');

  const recipients = await db.organization.findMany({
    where: { verificationStatus: 'APPROVED', accountStatus: 'ACTIVE', type: { in: ['NGO', 'SHELTER', 'COMMUNITY_KITCHEN'] } },
    include: { addresses: { where: { isPrimary: true }, take: 1 } },
  });

  const source = listing.organization.addresses[0];
  return recipients.map((org) => {
    const target = org.addresses[0];
    const distance = source?.latitude != null && source?.longitude != null && target?.latitude != null && target?.longitude != null
      ? haversineKm(source.latitude, source.longitude, target.latitude, target.longitude)
      : 10;
    const distanceScore = Math.max(0, 35 - Math.min(distance, 35));
    const capacityScore = org.maximumDailyCapacity && org.maximumDailyCapacity >= listing.servings ? 25 : 10;
    const verificationScore = 20;
    const categoryScore = 20;
    const score = Math.round(Math.min(100, distanceScore + capacityScore + verificationScore + categoryScore));
    const reasons = [
      distance <= 5 ? 'nearby collection location' : 'collection location is farther away',
      capacityScore === 25 ? 'has enough stated capacity' : 'capacity may be limited',
      'verified recipient organization',
      `handles ${listing.category.name.toLowerCase()} through the general food network`,
    ];
    return { organizationId: org.id, organizationName: org.name, score, distanceKm: Number(distance.toFixed(1)), reasons };
  }).sort((a, b) => b.score - a.score);
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const r = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}
