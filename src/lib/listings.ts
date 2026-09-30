import crypto from 'node:crypto';
import { db } from './db';

export async function reserveListing(listingId:string, organizationId:string, requestedById:string, quantity:number, start:Date,end:Date){
 if(!Number.isInteger(quantity)||quantity<=0) throw new Error('Quantity must be a positive whole number.');
 return db.$transaction(async tx=>{
  const [listing,org]=await Promise.all([tx.foodListing.findUnique({where:{id:listingId}}),tx.organization.findUnique({where:{id:organizationId},select:{verificationStatus:true,accountStatus:true}})]);
  if(!org||org.verificationStatus!=='APPROVED'||org.accountStatus!=='ACTIVE') throw new Error('Your organization must be verified and active before making reservations.');
  if(!listing) throw new Error('Listing not found.');
  if(!['PUBLISHED','PARTIALLY_RESERVED'].includes(listing.status)) throw new Error('This listing is not accepting reservations.');
  if(new Date()>=listing.availableUntil) throw new Error('This collection window has closed.');
  const remaining=listing.quantityListed-listing.quantityReserved-listing.quantityCollected;
  if(quantity>remaining) throw new Error(`Only ${remaining} portions remain available.`);
  const reference=`SP-${crypto.randomUUID().slice(0,8).toUpperCase()}`;
  const reservation=await tx.reservation.create({data:{reference,listingId,organizationId,requestedById,quantity,collectionWindowStart:start,collectionWindowEnd:end,items:{create:{listingId,quantity}}}});
  const newReserved=listing.quantityReserved+quantity;
  await tx.foodListing.update({where:{id:listingId},data:{quantityReserved:newReserved,status:newReserved+listing.quantityCollected>=listing.quantityListed?'FULLY_RESERVED':'PARTIALLY_RESERVED'}});
  const recipients=await tx.organizationMember.findMany({where:{organizationId},select:{userId:true}});
  if(recipients.length) await tx.notification.createMany({data:recipients.map(x=>({userId:x.userId,type:'RESERVATION_CREATED',title:'Reservation created',message:`Reservation ${reservation.reference} has been requested.`,relatedEntityType:'RESERVATION',relatedEntityId:reservation.id}))});
  return reservation;
 },{isolationLevel:'Serializable'});
}

export async function cancelReservation(reservationId:string, organizationId:string){
 return db.$transaction(async tx=>{
  const reservation=await tx.reservation.findUnique({where:{id:reservationId}});
  if(!reservation||reservation.organizationId!==organizationId) throw new Error('Reservation not found.');
  if(['COMPLETED','CANCELLED','REJECTED'].includes(reservation.status)) throw new Error('This reservation can no longer be cancelled.');
  const listing=await tx.foodListing.findUnique({where:{id:reservation.listingId}}); if(!listing) throw new Error('Listing not found.');
  await tx.reservation.update({where:{id:reservationId},data:{status:'CANCELLED',cancelledAt:new Date()}});
  const reserved=Math.max(0,listing.quantityReserved-reservation.quantity);
  const status=reserved===0?'PUBLISHED':reserved+listing.quantityCollected>=listing.quantityListed?'FULLY_RESERVED':'PARTIALLY_RESERVED';
  await tx.foodListing.update({where:{id:listing.id},data:{quantityReserved:reserved,status}});
  return {ok:true};
 },{isolationLevel:'Serializable'});
}
