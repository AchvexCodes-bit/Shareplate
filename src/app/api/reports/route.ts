import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { requireUser } from '@/lib/guards';
import { Role } from '@prisma/client';

const csv = (rows:string[][]) => rows.map(r=>r.map(v=>`"${String(v??'').replaceAll('"','""')}"`).join(',')).join('\n');
export async function GET(req:Request){
  try { await requireUser([Role.ADMIN]); const type=new URL(req.url).searchParams.get('type')||'daily'; const since=new Date(); if(type==='monthly') since.setDate(1); else since.setHours(0,0,0,0);
    const [listings,reservations,pickups,impacts]=await Promise.all([
      db.foodListing.findMany({where:{createdAt:{gte:since}},select:{reference:true,name:true,status:true,quantityListed:true,quantityReserved:true,quantityCollected:true,createdAt:true}}),
      db.reservation.findMany({where:{createdAt:{gte:since}},select:{reference:true,quantity:true,status:true,createdAt:true}}),
      db.pickupRequest.findMany({where:{windowStart:{gte:since}},select:{reference:true,status:true,expectedQuantity:true,collectedQuantity:true,deliveredQuantity:true,windowStart:true,deliveryAt:true}}),
      db.impactRecord.findMany({where:{recordedAt:{gte:since}},select:{portions:true,weightKg:true,recordedAt:true}})
    ]);
    const rows:string[][]=[['Report',type,'Generated',new Date().toISOString()],['Section','Reference','Status','Quantity','Date']];
    listings.forEach(x=>rows.push(['Listing',x.reference,x.status,String(x.quantityCollected),x.createdAt.toISOString()]));
    reservations.forEach(x=>rows.push(['Reservation',x.reference,x.status,String(x.quantity),x.createdAt.toISOString()]));
    pickups.forEach(x=>rows.push(['Pickup',x.reference,x.status,String(x.deliveredQuantity??x.collectedQuantity??x.expectedQuantity),x.windowStart.toISOString()]));
    impacts.forEach(x=>rows.push(['Impact','',`${x.weightKg??0} kg`,String(x.portions),x.recordedAt.toISOString()]));
    return new NextResponse(csv(rows),{headers:{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':`attachment; filename="shareplate-${type}-report.csv"`}});
  } catch { return NextResponse.json({error:'Admin access is required.'},{status:403}); }
}
