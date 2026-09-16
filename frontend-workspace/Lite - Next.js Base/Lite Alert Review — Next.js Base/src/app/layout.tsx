import type { Metadata } from "next";
import { InstitutionProvider } from "@/lib/ui/institutionContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "HazeWatch AI",
  description: "Transboundary haze early-warning dashboard",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <InstitutionProvider>{children}</InstitutionProvider>
      </body>
    </html>
  );
}
