import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "FleetPulse Intelligence",
  description: "Fleet maintenance operations, in one auditable workflow.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
