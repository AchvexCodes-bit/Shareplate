-- SharePlate Part 2 operational migration
ALTER TYPE "PickupStatus" ADD VALUE IF NOT EXISTS 'ACCEPTED';
ALTER TYPE "PickupStatus" ADD VALUE IF NOT EXISTS 'EN_ROUTE';
ALTER TYPE "PickupStatus" ADD VALUE IF NOT EXISTS 'ARRIVED';
ALTER TYPE "PickupStatus" ADD VALUE IF NOT EXISTS 'RESCHEDULED';
ALTER TYPE "ComplaintStatus" ADD VALUE IF NOT EXISTS 'ACTION_REQUIRED';
DO $$ BEGIN CREATE TYPE "PickupCondition" AS ENUM ('GOOD','ACCEPTABLE','DAMAGED','CONCERNING'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE "PickupRequest" ADD COLUMN IF NOT EXISTS "expectedQuantity" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "PickupRequest" ADD COLUMN IF NOT EXISTS "collectedQuantity" INTEGER;
ALTER TABLE "PickupRequest" ADD COLUMN IF NOT EXISTS "deliveredQuantity" INTEGER;
ALTER TABLE "PickupRequest" ADD COLUMN IF NOT EXISTS "collectionAt" TIMESTAMP(3);
ALTER TABLE "PickupRequest" ADD COLUMN IF NOT EXISTS "deliveryAt" TIMESTAMP(3);
ALTER TABLE "PickupRequest" ADD COLUMN IF NOT EXISTS "collectionNotes" TEXT;
ALTER TABLE "PickupRequest" ADD COLUMN IF NOT EXISTS "collectionPhotoUrl" TEXT;
ALTER TABLE "PickupRequest" ADD COLUMN IF NOT EXISTS "deliveryPhotoUrl" TEXT;
ALTER TABLE "PickupRequest" ADD COLUMN IF NOT EXISTS "deliveryCondition" "PickupCondition";
ALTER TABLE "DeliveryConfirmation" ADD COLUMN IF NOT EXISTS "receivedQuantity" INTEGER;
ALTER TABLE "DeliveryConfirmation" ADD COLUMN IF NOT EXISTS "condition" "PickupCondition";
ALTER TABLE "DeliveryConfirmation" ADD COLUMN IF NOT EXISTS "proofPhotoUrl" TEXT;
ALTER TABLE "Complaint" ADD COLUMN IF NOT EXISTS "category" TEXT NOT NULL DEFAULT 'GENERAL';
ALTER TABLE "Complaint" ADD COLUMN IF NOT EXISTS "evidenceUrl" TEXT;
ALTER TABLE "Complaint" ADD COLUMN IF NOT EXISTS "adminResponse" TEXT;
ALTER TABLE "Complaint" ADD COLUMN IF NOT EXISTS "resolution" TEXT;
ALTER TABLE "ImpactRecord" ADD COLUMN IF NOT EXISTS "pickupId" TEXT;
CREATE TABLE IF NOT EXISTS "SavedFood" (
  "id" TEXT NOT NULL,
  "organizationId" TEXT NOT NULL,
  "categoryId" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "unit" "QuantityUnit" NOT NULL,
  "servings" INTEGER NOT NULL,
  "ingredients" TEXT,
  "allergens" TEXT,
  "storageCondition" "StorageCondition",
  "handlingInstructions" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "SavedFood_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "SavedFood_organizationId_name_key" ON "SavedFood"("organizationId","name");
CREATE INDEX IF NOT EXISTS "SavedFood_organizationId_idx" ON "SavedFood"("organizationId");
CREATE INDEX IF NOT EXISTS "Address_latitude_longitude_idx" ON "Address"("latitude","longitude");
CREATE INDEX IF NOT EXISTS "FoodListing_organizationId_status_idx" ON "FoodListing"("organizationId","status");
CREATE INDEX IF NOT EXISTS "FoodListing_categoryId_status_idx" ON "FoodListing"("categoryId","status");
CREATE INDEX IF NOT EXISTS "FoodListing_availableUntil_idx" ON "FoodListing"("availableUntil");
CREATE INDEX IF NOT EXISTS "PickupRequest_status_windowStart_idx" ON "PickupRequest"("status","windowStart");
CREATE INDEX IF NOT EXISTS "PickupRequest_sourceOrganizationId_status_idx" ON "PickupRequest"("sourceOrganizationId","status");
CREATE INDEX IF NOT EXISTS "PickupRequest_destinationOrganizationId_status_idx" ON "PickupRequest"("destinationOrganizationId","status");
CREATE INDEX IF NOT EXISTS "PickupAssignment_courierId_assignedAt_idx" ON "PickupAssignment"("courierId","assignedAt");
CREATE INDEX IF NOT EXISTS "Notification_userId_readAt_createdAt_idx" ON "Notification"("userId","readAt","createdAt");
CREATE INDEX IF NOT EXISTS "Complaint_status_createdAt_idx" ON "Complaint"("status","createdAt");
CREATE INDEX IF NOT EXISTS "AuditLog_createdAt_idx" ON "AuditLog"("createdAt");
CREATE INDEX IF NOT EXISTS "ImpactRecord_recordedAt_idx" ON "ImpactRecord"("recordedAt");
CREATE INDEX IF NOT EXISTS "ImpactRecord_organizationId_recordedAt_idx" ON "ImpactRecord"("organizationId","recordedAt");
DO $$ BEGIN ALTER TABLE "SavedFood" ADD CONSTRAINT "SavedFood_organizationId_fkey" FOREIGN KEY ("organizationId") REFERENCES "Organization"("id") ON DELETE CASCADE ON UPDATE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE "SavedFood" ADD CONSTRAINT "SavedFood_categoryId_fkey" FOREIGN KEY ("categoryId") REFERENCES "FoodCategory"("id") ON DELETE RESTRICT ON UPDATE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE "ImpactRecord" ADD CONSTRAINT "ImpactRecord_pickupId_key" UNIQUE ("pickupId"); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
