import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Cloude Phone",
  description: "Cloud Android management panel",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
