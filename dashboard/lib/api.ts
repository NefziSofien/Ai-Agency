"use client";

import { useCallback, useEffect, useState } from "react";

export async function api<T = unknown>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: init?.method ?? "GET",
    headers: { "Content-Type": "application/json" },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    throw new Error(detail || `Erreur ${res.status}`);
  }
  return data as T;
}

/** Charge une ressource et la rafraîchit toutes les `intervalMs` (0 = pas de rafraîchissement). */
export function useApi<T>(path: string | null, intervalMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [path]);

  useEffect(() => {
    reload();
    if (!intervalMs) return;
    const id = setInterval(reload, intervalMs);
    return () => clearInterval(id);
  }, [reload, intervalMs]);

  return { data, error, reload };
}

export type Client = {
  id: string;
  name: string;
  website: string | null;
  has_omniroute_key: boolean;
  brand_kit: Record<string, unknown>;
  settings: Record<string, unknown>;
};

export type Run = {
  id: string;
  client_id: string;
  client_name: string;
  brief: string;
  departments: string[];
  source: string;
  status: string;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type Action = { id: string; department: string; kind: string; summary: string; payload: Record<string, unknown> };

export type Asset = { id: number; kind: string; key: string; prompt: string | null; url: string };

export type RunDetail = {
  run: Run;
  client: Client;
  assets: Asset[];
  usage: { input_tokens: number; output_tokens: number; calls: number };
  state: {
    plan?: { department: string; instruction: string }[];
    results?: Record<string, string>;
    review?: { approved: boolean; score: number; issues: string[]; feedback: string };
    revisions?: number;
    deliverable?: string;
    executed?: { id: string; kind: string; ok: boolean; result?: unknown; error?: string }[];
    decision?: { approved: boolean; feedback: string };
    interrupt?: { actions: Action[]; deliverable: string } | null;
    current?: { department: string } | null;
    next?: string[];
  };
};

export const STATUS_LABELS: Record<string, string> = {
  running: "En cours",
  awaiting_approval: "À valider",
  completed: "Terminé",
  rejected: "Rejeté",
  failed: "Échec",
};

export const DEPARTMENTS: Record<string, string> = {
  strategie: "Stratégie et veille",
  seo: "SEO et SEA",
  analytics: "Analytics et reporting",
  contenu: "Contenu et copywriting",
  visuels: "Visuels et vidéo IA",
  social: "Social media",
  crm: "CRM et prospection",
};

export function formatDate(iso: string) {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}
