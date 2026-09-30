import { db } from '@/lib/db';

export async function getImpactSummary() {
  const [food, portions, pickups, partners, recipients] = await Promise.all([
    db.impactRecord.aggregate({ _sum: { weightKg: true } }),
    db.impactRecord.aggregate({ _sum: { portions: true } }),
    db.pickupRequest.count({ where: { status: 'COMPLETED' } }),
    db.organization.count({ where: { accountStatus: 'ACTIVE', verificationStatus: 'APPROVED', type: { in: ['RESTAURANT','BAKERY','HOTEL','SUPERMARKET','CATERER','EVENT_ORGANIZER'] } } }),
    db.organization.count({ where: { accountStatus: 'ACTIVE', verificationStatus: 'APPROVED', type: { in: ['NGO','SHELTER','COMMUNITY_KITCHEN'] } } }),
  ]);

  return {
    foodKg: food._sum.weightKg ?? 0,
    portions: portions._sum.portions ?? 0,
    completedPickups: pickups,
    activeFoodPartners: partners,
    activeRecipientOrganizations: recipients,
  };
}

export async function getMonthlyImpact(months = 6) {
  const since = new Date();
  since.setMonth(since.getMonth() - months + 1);
  since.setDate(1);
  since.setHours(0, 0, 0, 0);

  const records = await db.impactRecord.findMany({
    where: { recordedAt: { gte: since } },
    select: { recordedAt: true, weightKg: true, portions: true },
    orderBy: { recordedAt: 'asc' },
  });

  const grouped = new Map<string, { weightKg: number; portions: number }>();
  for (const record of records) {
    const key = `${record.recordedAt.getUTCFullYear()}-${String(record.recordedAt.getUTCMonth() + 1).padStart(2, '0')}`;
    const current = grouped.get(key) ?? { weightKg: 0, portions: 0 };
    current.weightKg += record.weightKg ?? 0;
    current.portions += record.portions;
    grouped.set(key, current);
  }
  return [...grouped.entries()].map(([month, value]) => ({ month, ...value }));
}
