"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth";

interface Proxy {
  id: string; label: string; type: string; host: string; port: number;
  username: string | null; has_password: boolean; created_at: string;
}

export default function ProxiesPage() {
  const router = useRouter();
  const [proxies, setProxies] = useState<Proxy[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ label: "", type: "socks5", host: "", port: 1080, username: "", password: "" });
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    const a = auth.access(); if (!a) { router.push("/login"); return; }
    try { setProxies(await apiFetch<Proxy[]>("/api/v1/proxies", {}, a)); }
    catch (e: any) {
      if (e.message?.startsWith("401")) { auth.clear(); router.push("/login"); return; }
      setErr(e.message);
    }
  }, [router]);

  useEffect(() => { load(); }, [load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    const a = auth.access(); if (!a) return;
    try {
      await apiFetch("/api/v1/proxies", {
        method: "POST",
        body: JSON.stringify({
          label: form.label, type: form.type, host: form.host, port: Number(form.port),
          username: form.username || null, password: form.password || null,
        }),
      }, a);
      setShowForm(false);
      setForm({ label: "", type: "socks5", host: "", port: 1080, username: "", password: "" });
      load();
    } catch (e: any) { setErr(e.message); }
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this proxy?")) return;
    const a = auth.access(); if (!a) return;
    await apiFetch(`/api/v1/proxies/${id}`, { method: "DELETE" }, a);
    load();
  };

  return (
    <main className="min-h-screen">
      <header className="border-b border-border px-6 py-4 flex items-center justify-between gap-4">
        <Link href="/" className="text-zinc-400 hover:text-zinc-200 whitespace-nowrap">← Back</Link>
        <h1 className="text-lg font-semibold flex-1">Proxies</h1>
        <button onClick={() => setShowForm(s => !s)} className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 rounded">
          {showForm ? "Cancel" : "+ Add proxy"}
        </button>
      </header>

      <section className="max-w-3xl mx-auto p-6 space-y-4">
        {err && <div className="p-3 bg-red-500/10 border border-red-500/40 text-red-300 rounded text-sm">{err}</div>}

        {showForm && (
          <form onSubmit={create} className="bg-card border border-border rounded-lg p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <input placeholder="Label" required value={form.label} onChange={e => setForm({ ...form, label: e.target.value })}
                className="px-3 py-2 bg-zinc-800 rounded text-sm" />
              <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}
                className="px-3 py-2 bg-zinc-800 rounded text-sm">
                <option value="socks5">SOCKS5</option>
                <option value="http">HTTP / HTTPS</option>
              </select>
              <input placeholder="Host" required value={form.host} onChange={e => setForm({ ...form, host: e.target.value })}
                className="px-3 py-2 bg-zinc-800 rounded text-sm col-span-1" />
              <input placeholder="Port" type="number" required min={1} max={65535} value={form.port}
                onChange={e => setForm({ ...form, port: Number(e.target.value) })}
                className="px-3 py-2 bg-zinc-800 rounded text-sm" />
              <input placeholder="Username (optional)" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })}
                className="px-3 py-2 bg-zinc-800 rounded text-sm" />
              <input placeholder="Password (optional)" type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}
                className="px-3 py-2 bg-zinc-800 rounded text-sm" />
            </div>
            <button className="w-full py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium">Create</button>
          </form>
        )}

        {proxies.length === 0 ? (
          <div className="text-center py-12 text-zinc-400">No proxies yet.</div>
        ) : (
          <div className="space-y-2">
            {proxies.map(p => (
              <div key={p.id} className="bg-card border border-border rounded-lg p-3 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="font-medium truncate">{p.label}</div>
                  <div className="text-xs text-zinc-400">
                    {p.type} • {p.host}:{p.port} {p.username && <>• user: {p.username}</>} {p.has_password && <>• 🔒 pw stored</>}
                  </div>
                </div>
                <button onClick={() => remove(p.id)} className="px-3 py-1.5 text-xs bg-red-700/40 hover:bg-red-700/60 rounded whitespace-nowrap">Delete</button>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
