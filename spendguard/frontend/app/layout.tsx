import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SpendGuard",
  description: "Let agents spend without holding the keys.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans text-slate-200 antialiased">{children}</body>
    </html>
  );
}
