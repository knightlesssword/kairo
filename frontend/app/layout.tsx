import type { Metadata } from "next";
import { Cinzel, Noto_Sans_JP, Geist_Mono } from "next/font/google";
import "./globals.css";

const cinzel = Cinzel({
  variable: "--font-cinzel",
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  display: "swap",
});

const notoSans = Noto_Sans_JP({
  variable: "--font-noto",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "kairo",
  description: "an ai that knows your anime.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${cinzel.variable} ${notoSans.variable} ${geistMono.variable} h-full`}
    >
      <body className="min-h-full flex flex-col bg-void text-text antialiased">
        {children}
      </body>
    </html>
  );
}
