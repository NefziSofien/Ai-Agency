"use client";

import { useState } from "react";
import { api, useApi, type Client } from "@/lib/api";

const BRAND_FIELDS: [string, string][] = [
  ["positionnement", "Positionnement et proposition de valeur"],
  ["offres", "Offres, produits, prix"],
  ["cibles", "Cibles et personas"],
  ["ton", "Ton de voix"],
  ["valeurs", "Valeurs"],
  ["interdits", "Interdits (mots, sujets, promesses)"],
  ["charte_graphique", "Charte graphique (couleurs, typographies, style visuel)"],
  ["concurrents", "Concurrents"],
  ["exemples", "Exemples de contenus réussis"],
];

const DEFAULT_SETTINGS = {
  timezone: "Africa/Tunis",
  daily_watch: false,
  weekly_report: false,
  crm_followups: false,
  ga4_property_id: "",
  search_console_site: "",
  google_ads_customer_id: "",
  meta_ad_account_id: "",
  postiz_integration_ids: [],
  listmonk_list_ids: [],
};

type Form = {
  id?: string;
  name: string;
  website: string;
  omniroute_key: string;
  brand: Record<string, string>;
  settings: string;
};

const empty = (): Form => ({
  name: "",
  website: "",
  omniroute_key: "",
  brand: {},
  settings: JSON.stringify(DEFAULT_SETTINGS, null, 2),
});

export default function ClientsPage() {
  const { data, error, reload } = useApi<Client[]>("/clients");
  const [form, setForm] = useState<Form>(empty());
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function edit(c: Client) {
    setFormError(null);
    setForm({
      id: c.id,
      name: c.name,
      website: c.website ?? "",
      omniroute_key: "",
      brand: Object.fromEntries(Object.entries(c.brand_kit).map(([k, v]) => [k, String(v)])),
      settings: JSON.stringify({ ...DEFAULT_SETTINGS, ...c.settings }, null, 2),
    });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    let settings: Record<string, unknown>;
    try {
      settings = JSON.parse(form.settings);
    } catch {
      setFormError("Les paramètres doivent être un JSON valide.");
      return;
    }
    setSaving(true);
    const body = {
      name: form.name,
      website: form.website || null,
      omniroute_key: form.omniroute_key || null,
      brand_kit: Object.fromEntries(Object.entries(form.brand).filter(([, v]) => v.trim())),
      settings,
    };
    try {
      await api(form.id ? `/clients/${form.id}` : "/clients", { method: form.id ? "PUT" : "POST", body });
      setForm(empty());
      await reload();
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(c: Client) {
    if (!confirm(`Supprimer ${c.name} et tout son historique ?`)) return;
    await api(`/clients/${c.id}`, { method: "DELETE" });
    if (form.id === c.id) setForm(empty());
    await reload();
  }

  return (
    <div className="grid" style={{ gridTemplateColumns: "1fr 520px" }}>
      <section className="panel">
        <h1>Clients</h1>
        {error && <div className="error">{error}</div>}
        <table>
          <thead>
            <tr>
              <th>Client</th>
              <th>Clé OmniRoute</th>
              <th>Automatisations</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data?.map((c) => (
              <tr key={c.id}>
                <td>
                  <strong>{c.name}</strong>
                  <div className="muted">{c.website}</div>
                </td>
                <td>{c.has_omniroute_key ? "dédiée" : <span className="muted">par défaut</span>}</td>
                <td className="muted">
                  {[
                    c.settings.daily_watch && "veille",
                    c.settings.weekly_report && "rapport hebdo",
                    c.settings.crm_followups && "relances CRM",
                  ]
                    .filter(Boolean)
                    .join(", ") || "aucune"}
                </td>
                <td className="row" style={{ justifyContent: "flex-end" }}>
                  <button className="secondary" onClick={() => edit(c)}>
                    Modifier
                  </button>
                  <button className="danger" onClick={() => remove(c)}>
                    Supprimer
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data?.length === 0 && <p className="muted">Aucun client.</p>}
      </section>

      <form className="panel" onSubmit={save}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>{form.id ? `Modifier ${form.name}` : "Nouveau client"}</h2>
          {form.id && (
            <button type="button" className="secondary" onClick={() => setForm(empty())}>
              Annuler
            </button>
          )}
        </div>
        <label>Nom</label>
        <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        <label>Site web</label>
        <input type="url" value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
        <label>Clé OmniRoute dédiée (optionnel)</label>
        <input
          type="password"
          value={form.omniroute_key}
          placeholder={form.id ? "Laisser vide pour conserver la clé actuelle" : "Sinon, la clé par défaut est utilisée"}
          onChange={(e) => setForm({ ...form, omniroute_key: e.target.value })}
        />

        <h2 style={{ marginTop: 20 }}>Brand kit</h2>
        {BRAND_FIELDS.map(([key, label]) => (
          <div key={key}>
            <label>{label}</label>
            <textarea
              style={{ minHeight: 60 }}
              value={form.brand[key] ?? ""}
              onChange={(e) => setForm({ ...form, brand: { ...form.brand, [key]: e.target.value } })}
            />
          </div>
        ))}

        <label>Paramètres et intégrations (JSON)</label>
        <textarea className="code" value={form.settings} onChange={(e) => setForm({ ...form, settings: e.target.value })} />

        {formError && <div className="error">{formError}</div>}
        <div style={{ marginTop: 14 }}>
          <button disabled={saving}>{saving ? "Enregistrement…" : "Enregistrer"}</button>
        </div>
      </form>
    </div>
  );
}
