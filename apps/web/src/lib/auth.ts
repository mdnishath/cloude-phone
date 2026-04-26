"use client";

import { apiFetch } from "./api";

const ACCESS_KEY = "cloude.access";
const REFRESH_KEY = "cloude.refresh";

export interface TokenPair {
  access: string;
  refresh: string;
  token_type: string;
}

export const auth = {
  save(p: TokenPair) {
    if (typeof window === "undefined") return;
    localStorage.setItem(ACCESS_KEY, p.access);
    localStorage.setItem(REFRESH_KEY, p.refresh);
  },
  clear() {
    if (typeof window === "undefined") return;
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  access(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(ACCESS_KEY);
  },
  refresh(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(REFRESH_KEY);
  },
  async login(email: string, password: string): Promise<TokenPair> {
    const tp = await apiFetch<TokenPair>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    auth.save(tp);
    return tp;
  },
  async redeem(token: string, email: string, password: string): Promise<TokenPair> {
    const tp = await apiFetch<TokenPair>("/api/v1/auth/redeem-invite", {
      method: "POST",
      body: JSON.stringify({ token, email, password }),
    });
    auth.save(tp);
    return tp;
  },
  logout() {
    auth.clear();
    if (typeof window !== "undefined") window.location.href = "/login";
  },
};
