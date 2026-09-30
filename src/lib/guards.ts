import { Role } from '@prisma/client';
import { getSession } from '@/lib/session';
import { db } from '@/lib/db';

export async function requireUser(roles?: Role[]) {
  const session = await getSession();
  if (!session) throw new Error('UNAUTHENTICATED');
  const user = await db.user.findUnique({ where: { id: session.userId }, include: { memberships: true, courier: true } });
  if (!user || user.accountStatus !== 'ACTIVE') throw new Error('FORBIDDEN');
  const role = user.memberships[0]?.role;
  if (roles?.length && (!role || !roles.includes(role))) throw new Error('FORBIDDEN');
  return { user, role, organizationId: user.memberships[0]?.organizationId };
}
