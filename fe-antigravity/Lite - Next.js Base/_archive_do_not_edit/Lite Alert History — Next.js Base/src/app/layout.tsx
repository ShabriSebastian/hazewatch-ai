import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HazeWatch AI",
  description: "Transboundary haze early-warning dashboard",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
