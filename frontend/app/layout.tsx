import type { Metadata } from "next";
import { Inter, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";

// Two font families on purpose: Inter for UI/Latin text (clean, standard),
// Noto Sans Devanagari for Hindi — without an explicit Devanagari-covering
// face, Hindi text can render with the wrong glyph shapes or fall back to
// a boxy system font depending on the judge's machine.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const notoDevanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "600"],
  variable: "--font-devanagari",
});

export const metadata: Metadata = {
  title: "Saathi (साथी)",
  description: "Voice-first Hindi companion for hospital admission and insurance",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="hi">
      <body className={`${inter.variable} ${notoDevanagari.variable} font-sans antialiased`}>
        {children}
      </body>
    </html>
  );
}
