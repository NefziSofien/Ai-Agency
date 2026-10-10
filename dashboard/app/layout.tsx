import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agence IA",
  description: "Pilotage des agents de l'agence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
            Agence IA
          </Link>
          <nav>
            <Link href="/">Briefs</Link>
            <Link href="/approvals">Validations</Link>
            <Link href="/clients">Clients</Link>
            <Link href="/usage">Usage et santé</Link>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
