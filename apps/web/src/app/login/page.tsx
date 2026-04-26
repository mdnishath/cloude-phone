"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { auth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <main className="min-h-screen grid place-items-center px-4">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setLoading(true);
          setErr(null);
          try {
            await auth.login(email, password);
            router.push("/");
          } catch (e: any) {
            setErr(e.message);
          } finally {
            setLoading(false);
          }
        }}
        className="w-full max-w-sm space-y-4 p-6 bg-card rounded-lg border border-border"
      >
        <div>
          <h1 className="text-2xl font-semibold">Cloude Phone</h1>
          <p className="text-sm text-zinc-400 mt-1">Sign in to manage your devices</p>
        </div>
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email"
          type="email"
          autoComplete="email"
          required
          className="w-full px-3 py-2 bg-zinc-800 rounded outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password"
          type="password"
          autoComplete="current-password"
          required
          className="w-full px-3 py-2 bg-zinc-800 rounded outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          disabled={loading}
          className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded font-medium"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
        {err && <p className="text-red-400 text-sm">{err}</p>}
        <p className="text-xs text-zinc-500 text-center pt-2">
          Have an invite token?{" "}
          <Link href="/redeem" className="text-blue-400 hover:underline">
            Redeem here
          </Link>
        </p>
      </form>
    </main>
  );
}
