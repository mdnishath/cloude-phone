"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth";

interface Profile {
  id: string;
  name: string;
  android_version: string;
  screen_width: number;
  screen_height: number;
  ram_mb: number;
  manufacturer: string;
  model: string;
}

interface Proxy {
  id: string;
  label: string;
  host: string;
  port: number;
}

export default function NewPhonePage() {
  const router = useRouter();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [proxies, setProxies] = useState<Proxy[]>([]);
  const [name, setName] = useState("");
  const [profileId, setProfileId] = useState("");
  const [proxyId, setProxyId] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const a = auth.access();
    if (!a) { router.push("/login"); return; }
    Promise.all([
      apiFetch<Profile[]>("/api/v1/device-profiles", {}, a),
      apiFetch<Proxy[]>("/api/v1/proxies", {}, a),
    ])
      .then(([p, x]) => { setProfiles(p); setProxies(x); if (p[0]) setProfileId(p[0].id); })
      .catch(e => setErr(e.message));
  }, [router]);

  return (
    <main className="min-h-screen">
      <header className="border-b border-border px-6 py-4 flex items-center justify-between">
        <Link href="/" className="text-zinc-400 hover:text-zinc-200">← Back to phones</Link>
        <h1 className="text-lg font-semibold">Create phone</h1>
        <div />
      </header>

      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSubmitting(true); setErr(null);
          const a = auth.access(); if (!a) return;
          try {
            const dev = await apiFetch<{ id: string }>("/api/v1/devices", {
              method: "POST",
              body: JSON.stringify({ name, profile_id: profileId, proxy_id: proxyId || null }),
            }, a);
            router.push(`/phones/${dev.id}`);
          } catch (e: any) {
            setErr(e.message);
          } finally {
            setSubmitting(false);
          }
        }}
        className="max-w-xl mx-auto p-6 space-y-6"
      >
        <div className="space-y-2">
          <label className="text-sm font-medium block">Phone name</label>
          <input value={name} onChange={(e) => setName(e.target.value)}
            placeholder="e.g. My WhatsApp Phone" required maxLength={120}
            className="w-full px-3 py-2 bg-zinc-800 rounded outline-none focus:ring-2 focus:ring-blue-500" />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium block">Hardware profile</label>
          <select value={profileId} onChange={(e) => setProfileId(e.target.value)} required
            className="w-full px-3 py-2 bg-zinc-800 rounded outline-none focus:ring-2 focus:ring-blue-500">
            {profiles.map(p => (
              <option key={p.id} value={p.id}>
                {p.name} — {p.manufacturer} {p.model} • {p.ram_mb}MB
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium block">Proxy (optional)</label>
          <select value={proxyId} onChange={(e) => setProxyId(e.target.value)}
            className="w-full px-3 py-2 bg-zinc-800 rounded outline-none focus:ring-2 focus:ring-blue-500">
            <option value="">— None (direct egress) —</option>
            {proxies.map(p => <option key={p.id} value={p.id}>{p.label} ({p.host}:{p.port})</option>)}
          </select>
          {proxies.length === 0 && (
            <p className="text-xs text-zinc-500">No proxies yet — <Link href="/proxies" className="text-blue-400 hover:underline">add one</Link>.</p>
          )}
        </div>

        {err && <div className="p-3 bg-red-500/10 border border-red-500/40 text-red-300 rounded text-sm">{err}</div>}

        <button disabled={submitting || !name || !profileId}
          className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded font-medium">
          {submitting ? "Creating..." : "Create phone"}
        </button>
      </form>
    </main>
  );
}
