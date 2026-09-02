import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Crosswalk Vision — inspection priority",
  description:
    "Lower Manhattan pedestrian-crossing inspection list from LION, 2024 NYS orthos, 311, school zones, and Vision Zero crashes."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
