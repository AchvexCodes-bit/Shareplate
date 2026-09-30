# SharePlate

**Good food deserves another table.**

SharePlate is a surplus food redistribution platform connecting food partners with verified recipient organizations.

## Part 1 + Part 2

The current foundation includes:
- Role-based authentication and organization verification
- PostgreSQL + Prisma relational data model
- Food listings, safety records and expiry handling
- Transaction-safe reservation and cancellation rules
- Courier assignment and mobile pickup workflow
- Validated pickup state transitions with history
- Collection and delivery quantity reconciliation
- Notifications and incident/complaint workflow
- Database-backed impact aggregation
- Admin operations center and operational alerts
- CSV reporting
- Explainable recipient matching
- Leaflet/OpenStreetMap network map
- Reusable saved-food records
- Audit logging and object-level authorization helpers
- Responsive, accessibility-conscious UI

## Operational flow

`Listing → Reservation → Pickup Assignment → Accepted → En Route → Arrived → Collected → Delivered → Completed`

Every important operational transition is persisted. Reservations affect inventory inside database transactions, and completed pickups create impact records.

## Stack

- Next.js 15 / React 19
- TypeScript
- Tailwind CSS
- PostgreSQL
- Prisma ORM
- Secure HTTP-only sessions
- Leaflet + OpenStreetMap
- Recharts dependency for analytics extensions

## Development

```bash
npm install
npx prisma generate
npx prisma migrate dev
npm run db:seed
npm run dev
```

Set `DATABASE_URL` and `AUTH_SECRET` in the environment. Use a non-production seed credential through `SEED_PASSWORD` when running the demo seed.

Food providers remain responsible for complying with applicable food-safety requirements. SharePlate does not guarantee food safety.
