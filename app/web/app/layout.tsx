import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geist = Geist({
  subsets: ["latin-ext"],
  variable: "--font-geist"
});

export const metadata: Metadata = {
  title: "AI Kids Music Studio",
  description: "Local operator cockpit for AI-assisted kids music production."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pl">
      <body className={`${geist.variable} antialiased`}>{children}</body>
    </html>
  );
}
