import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Crosswalks",
  description: "Lower Manhattan crosswalk attention browser"
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
