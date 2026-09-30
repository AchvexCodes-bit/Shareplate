import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { requireUser } from '@/lib/guards';

export async function GET() {
  try { const { user } = await requireUser(); const data = await db.notification.findMany({ where:{ userId:user.id }, orderBy:{createdAt:'desc'}, take:100 }); return NextResponse.json({data}); }
  catch { return NextResponse.json({error:'Please sign in to view notifications.'},{status:401}); }
}

export async function PATCH(req:Request) {
  try { const { user } = await requireUser(); const body=await req.json(); if(body.all){ await db.notification.updateMany({where:{userId:user.id,readAt:null},data:{readAt:new Date()}}); } else if(body.id){ await db.notification.updateMany({where:{id:String(body.id),userId:user.id},data:{readAt:new Date()}}); } return NextResponse.json({ok:true}); }
  catch { return NextResponse.json({error:'We could not update notifications.'},{status:400}); }
}
