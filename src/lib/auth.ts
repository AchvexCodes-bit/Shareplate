import bcrypt from 'bcryptjs';
import { Role } from '@prisma/client';
export async function hashPassword(password:string){return bcrypt.hash(password,12)}
export async function verifyPassword(password:string,hash:string){return bcrypt.compare(password,hash)}
export function hasRole(userRole:Role, allowed:Role[]){return allowed.includes(userRole)}
