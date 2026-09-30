import {NextResponse} from 'next/server';
import {expireListings} from '@/lib/expiry';
export async function GET(req:Request){const configured=process.env.CRON_SECRET;const provided=req.headers.get('authorization')?.replace(/^Bearer\s+/i,'');if(!configured||provided!==configured)return NextResponse.json({error:'Unauthorized.'},{status:401});try{return NextResponse.json({expired:await expireListings()});}catch{return NextResponse.json({error:'Expiry processing failed.'},{status:500});}}
