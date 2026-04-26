"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth";

interface Device {
  id: string;
  name: string;
  state: string;
  state_reason: string | null;
  adb_host_port: number | null;
  profile_id: string;
  proxy_id: string | null;
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
}

interface Me {
  id: string;
  email: string;
  role: string;
  quota_instances: number;
}

const STATE_COLOR: Record<string, string> = {
  creating: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40",
  running:  "bg-green-500/20 text-green-300 border-green-500/40",
  stopping: "bg-orange-500/20 text-orange-300 border-orange-500/40",
  stopped:  "bg-zinc-500/20 text-zinc-300 border-zinc-500/40",
  error:    "bg-red-500/20 text-red-300 border-red-500/40",
  deleted:  "bg-zinc-700 text-zinc-500 border-zinc-700",
};

export default function HomePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const a = auth.access();
    if (!a) { router.push("/login"); return; }
    try {
      const [meData, devs] = await Promise.all([
        apiFetch<Me>("/api/v1/me", {}, a),
        apiFetch<Device[]>("/api/v1/devices", {}, a),
      ]);
      setMe(meData); setDevices(devs); setError(null);
    } catch (e: any) {
      if (e.message?.startsWith("401")) { auth.clear(); router.push("/login"); return; }
      setError(e.message);
    } finally { setLoading(false); }
  }, [router]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { const i = setInterval(load, 3000); return () => clearInterval(i); }, [load]);

  const callAction = async (id: string, action: "start" | "stop") => {
    const a = auth.access(); if (!a) return;
    try { await apiFetch(`/api/v1/devices/${id}/${action}`, { method: "POST" }, a); load(); }
    catch (e: any) { setError(e.message); }
  };

  const callDelete = async (id: string) => {
    if (!confirm("Delete this phone?")) return;
    const a = auth.access(); if (!a) return;
    try { await apiFetch(`/api/v1/devices/${id}`, { method: "DELETE" }, a); load(); }
    catch (e: any) { setError(e.message); }
  };

  if (loading) return <main className="min-h-screen grid place-items-center text-zinc-400">Loading…</main>;

  return (
    <main className="min-h-screen">
      <header className="border-b border-border px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Cloude Phone</h1>
          {me && <p className="text-xs text-zinc-400">{me.email} • {me.role} • quota {me.quota_instances}</p>}
        </div>
        <div className="flex gap-2">
          <Link href="/proxies" className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded">Proxies</Link>
          <Link href="/phones/new" className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 rounded">+ New phone</Link>
          <button onClick={() => auth.logout()} className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded">Logout</button>
        </div>
      </header>

      <section className="p-6">
        {error && <div className="mb-4 p-3 bg-red-500/10 border border-red-500/40 text-red-300 rounded">{error}</div>}

        {devices.length === 0 ? (
          <div className="text-center py-16 text-zinc-400">
            <p className="text-lg mb-3">No phones yet.</p>
            <Link href="/phones/new" className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded">Create your first phone</Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {devices.map(d => (
              <div key={d.id} className="bg-card border border-border rounded-lg p-4 space-y-3">
                <div className="flex items-start justify-between">
                  <Link href={`/phones/${d.id}`} className="font-medium hover:text-blue-400 truncate flex-1">
                    📱 {d.name}
                  </Link>
                  <span className={`text-xs px-2 py-0.5 rounded border ${STATE_COLOR[d.state] || "bg-zinc-800"}`}>{d.state}</span>
                </div>

                <dl className="text-xs text-zinc-400 space-y-1">
                  <div>ADB port: <span className="text-zinc-200">{d.adb_host_port ?? "—"}</span></div>
                  {d.state_reason && <div className="text-red-300">{d.state_reason}</div>}
                </dl>

                <div className="flex gap-2 pt-2 border-t border-border">
                  {d.state === "running" && (
                    <button onClick={() => callAction(d.id, "stop")} className="flex-1 text-xs py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded">Stop</button>
                  )}
                  {(d.state === "stopped" || d.state === "error") && (
                    <button onClick={() => callAction(d.id, "start")} className="flex-1 text-xs py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded">Start</button>
                  )}
                  <button onClick={() => callDelete(d.id)} className="flex-1 text-xs py-1.5 bg-red-700/40 hover:bg-red-700/60 rounded">Delete</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
