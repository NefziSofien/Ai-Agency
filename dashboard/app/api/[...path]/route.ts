import { NextRequest } from "next/server";

const API_URL = process.env.AGENCE_API_INTERNAL_URL ?? "http://127.0.0.1:8000";
const API_KEY = process.env.AGENCE_API_KEY ?? "";

async function proxy(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = `${API_URL}/${path.join("/")}${req.nextUrl.search}`;
  const init: RequestInit = {
    method: req.method,
    headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
    cache: "no-store",
  };
  if (!["GET", "HEAD"].includes(req.method)) init.body = await req.text();
  try {
    const res = await fetch(url, init);
    return new Response(res.status === 204 ? null : await res.text(), {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
    });
  } catch {
    return Response.json({ detail: `API de l'agence injoignable (${API_URL}).` }, { status: 502 });
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
