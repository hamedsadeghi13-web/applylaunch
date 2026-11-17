// Supabase Edge Function (Deno) – e-mail notification service. STATUS: sketch, not deployed or tested.
// Schedule with pg_cron / Supabase Scheduler. Secrets (RESEND_API_KEY, SUPABASE_SERVICE_ROLE_KEY) are set as function secrets, never in the repo.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

Deno.serve(async () => {
  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: prefs } = await db.from("notification_prefs").select("*").eq("email_enabled", true);
  for (const p of prefs ?? []) {
    const since = p.last_sent ?? new Date(Date.now() - 7 * 864e5).toISOString();
    const f = p.filters ?? {};
    let q = db.from("positions").select("title,inst,city,deadline,url").gte("first_seen", since.slice(0, 10)).limit(20);
    if (f.cc) q = q.eq("cc", f.cc);
    if (f.type) q = q.eq("type", f.type);
    const { data: rows } = await q;
    if (!rows?.length) continue;
    const { data: user } = await db.auth.admin.getUserById(p.user_id);
    const html = rows.map((r) => `<p><a href="${r.url}">${r.title}</a><br>${r.inst ?? ""} · ${r.city ?? ""} · deadline ${r.deadline ?? "not stated"}</p>`).join("");
    await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${Deno.env.get("RESEND_API_KEY")}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: "ApplyLaunch <news@YOUR-DOMAIN>", to: user.user!.email, subject: "New opportunities for you", html }),
    });
    await db.from("notification_prefs").update({ last_sent: new Date().toISOString() }).eq("user_id", p.user_id);
  }
  return new Response("ok");
});
