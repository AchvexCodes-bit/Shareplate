import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { requireUser } from '@/lib/guards';
import { Role } from '@prisma/client';

export async function GET() {
  try {
    await requireUser([Role.ADMIN]);
    const now = new Date();
    const soon = new Date(now.getTime() + 60 * 60 * 1000);
    const [activeListings, reservations, pickupsToday, complaints, expiring, missed, unverified, failed, statusCounts, categories, pickups, monthly] = await Promise.all([
      db.foodListing.count({ where: { status: { in: ['PUBLISHED','PARTIALLY_RESERVED','FULLY_RESERVED','PICKUP_SCHEDULED'] }, availableUntil: { gt: now } } }),
      db.reservation.count({ where: { createdAt: { gte: new Date(now.getTime() - 24*60*60*1000) }, status: { notIn: ['CANCELLED','REJECTED'] } } }),
      db.pickupRequest.count({ where: { windowStart: { gte: new Date(now.setHours(0,0,0,0)) }, windowEnd: { lt: new Date(new Date().setHours(23,59,59,999)) } } }),
      db.complaint.count({ where: { status: { in: ['OPEN','IN_REVIEW','ACTION_REQUIRED'] } } }),
      db.foodListing.findMany({ where: { availableUntil: { gt: new Date(), lte: soon }, status: { in: ['PUBLISHED','PARTIALLY_RESERVED'] } }, select: { id:true,reference:true,name:true,availableUntil:true }, take:20 }),
      db.pickupRequest.findMany({ where: { windowEnd: { lt: new Date() }, status: { in: ['ASSIGNED','ACCEPTED','EN_ROUTE','ARRIVED'] } }, select: { id:true,reference:true,windowEnd:true }, take:20 }),
      db.organization.findMany({ where: { verificationStatus: 'PENDING' }, select: { id:true,name:true,createdAt:true }, take:20 }),
      db.pickupRequest.findMany({ where: { status: 'ISSUE_REPORTED' }, select: { id:true,reference:true,issueNotes:true }, take:20 }),
      db.foodListing.groupBy({ by:['status'], _count:{_all:true} }),
      db.foodListing.groupBy({ by:['categoryId'], _count:{_all:true}, _sum:{quantityCollected:true} }),
      db.pickupRequest.groupBy({ by:['status'], _count:{_all:true} }),
      db.impactRecord.findMany({ where:{ recordedAt:{ gte:new Date(new Date().setMonth(new Date().getMonth()-6)) } }, select:{recordedAt:true,weightKg:true,portions:true}, orderBy:{recordedAt:'asc'} }),
    ]);
    return NextResponse.json({ data:{metrics:{activeListings,reservations,pickupsToday,issues:complaints},needsAttention:{expiring,missed,unverified,failed},listingStatus:statusCounts,categories,pickups,monthlyImpact:monthly} });
  } catch { return NextResponse.json({ error:'Admin access is required.' }, { status:403 }); }
}
