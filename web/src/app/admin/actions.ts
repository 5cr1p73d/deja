"use server";

import { revalidatePath } from "next/cache";
import { auth } from "@/auth";
import { prisma } from "@/lib/db";
import { logAudit } from "@/lib/audit";

async function requireAdmin() {
  const session = await auth();
  if (!session?.user?.id || session.user.role !== "ADMIN") {
    throw new Error("Accesso negato");
  }
  return session.user;
}

export async function setUserRole(userId: string, role: "USER" | "ADMIN") {
  const admin = await requireAdmin();
  if (userId === admin.id && role !== "ADMIN") {
    throw new Error("Non puoi rimuovere il tuo stesso ruolo admin");
  }
  await prisma.user.update({ where: { id: userId }, data: { role } });
  await logAudit({ action: "role_change", actorId: admin.id, target: userId, meta: { role } });
  revalidatePath("/admin/users");
}

export async function setUserBanned(userId: string, banned: boolean) {
  const admin = await requireAdmin();
  if (userId === admin.id) throw new Error("Non puoi bannare te stesso");
  await prisma.user.update({ where: { id: userId }, data: { banned } });
  await logAudit({
    action: banned ? "user_ban" : "user_unban",
    actorId: admin.id,
    target: userId,
  });
  revalidatePath("/admin/users");
}

export async function deleteUser(userId: string) {
  const admin = await requireAdmin();
  if (userId === admin.id) throw new Error("Non puoi eliminare te stesso");
  await prisma.user.delete({ where: { id: userId } });
  await logAudit({ action: "user_delete", actorId: admin.id, target: userId });
  revalidatePath("/admin/users");
}

export async function setWaitlistStatus(
  id: string,
  status: "PENDING" | "INVITED" | "CONVERTED"
) {
  const admin = await requireAdmin();
  await prisma.waitlistEntry.update({ where: { id }, data: { status } });
  await logAudit({ action: "waitlist_status", actorId: admin.id, target: id, meta: { status } });
  revalidatePath("/admin/waitlist");
}

export async function deleteWaitlistEntry(id: string) {
  const admin = await requireAdmin();
  await prisma.waitlistEntry.delete({ where: { id } });
  revalidatePath("/admin/waitlist");
}

export async function setMessageStatus(
  id: string,
  status: "NEW" | "READ" | "ARCHIVED"
) {
  const admin = await requireAdmin();
  await prisma.contactMessage.update({ where: { id }, data: { status } });
  revalidatePath("/admin/messages");
}

export async function toggleFeatureFlag(key: string, enabled: boolean) {
  const admin = await requireAdmin();
  await prisma.featureFlag.update({ where: { key }, data: { enabled } });
  await logAudit({ action: "flag_toggle", actorId: admin.id, target: key, meta: { enabled } });
  revalidatePath("/admin");
  revalidatePath("/admin/flags");
}
