import crypto from 'crypto'; import { cookies } from 'next/headers';
const secret=()=>process.env.AUTH_SECRET||'development-only-secret-change-me';
function sign(payload:string){return crypto.createHmac('sha256',secret()).update(payload).digest('hex')}
export async function setSession(userId:string){const payload=Buffer.from(JSON.stringify({userId,exp:Date.now()+1000*60*60*8})).toString('base64url');(await cookies()).set('shareplate_session',`${payload}.${sign(payload)}`,{httpOnly:true,sameSite:'lax',secure:process.env.NODE_ENV==='production',path:'/',maxAge:60*60*8});}
export async function getSession(){const raw=(await cookies()).get('shareplate_session')?.value;if(!raw)return null;const [payload,sig]=raw.split('.');if(!payload||!sig||!crypto.timingSafeEqual(Buffer.from(sig),Buffer.from(sign(payload))))return null;try{const data=JSON.parse(Buffer.from(payload,'base64url').toString());if(data.exp<Date.now())return null;return data as {userId:string,exp:number}}catch{return null}}
export async function clearSession(){(await cookies()).delete('shareplate_session')}
