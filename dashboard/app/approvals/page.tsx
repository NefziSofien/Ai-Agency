"use client";

import Link from "next/link";
import { formatDate, useApi } from "@/lib/api";

type Pending = { id: string; client_name: string; brief: string; updated_at: string };

export default function ApprovalsPage() {
  const { data, error } = useApi<Pending[]>("/approvals", 5000);
  return (
    <div className="panel">
      <h1>Livrables en attente de validation</h1>
      {error && <div className="error">{error}</div>}
      {data?.length === 0 && <p className="muted">Rien à valider.</p>}
      <table>
        <tbody>
          {data?.map((r) => (
            <tr key={r.id}>
              <td className="muted" style={{ width: 140 }}>
                {formatDate(r.updated_at)}
              </td>
              <td style={{ width: 200 }}>{r.client_name}</td>
              <td>
                <Link href={`/runs/${r.id}`}>{r.brief}</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
