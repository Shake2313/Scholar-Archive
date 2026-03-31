import type { Metadata } from "next";
import { Cormorant_Garamond, Noto_Serif_KR } from "next/font/google";

import { SiteHeader } from "@/components/site-header";

import "./globals.css";

const displayFont = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-display",
});

const bodyFont = Noto_Serif_KR({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "Scholar Archive",
  description: "Historical document archive for digitized originals and Korean translations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${displayFont.variable} ${bodyFont.variable}`}>
        <div className="pageFrame">
          <SiteHeader />
          <main className="pageContent">{children}</main>
        </div>
      </body>
    </html>
  );
}
