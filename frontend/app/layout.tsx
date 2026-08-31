// app/layout.tsx — the root document: fonts, metadata and the global provider composition.
//
// what  : Defines the HTML shell, loads the two AERIS typefaces, declares SEO/social metadata, and mounts
//         the application providers.
// where : Wraps every route in the application.
// how   : Kept deliberately thin — no layout structure, no business logic. The application shell (rail,
//         header, panels) is composed per surface so each of the seven pages can arrange its own zones
//         while sharing the same shell components. Fonts are loaded through next/font so they are
//         self-hosted and produce no layout shift on first paint.

import type { Metadata, Viewport } from "next";
import { Geist, JetBrains_Mono } from "next/font/google";

import { AppProviders } from "@/lib/providers/app-providers";
import { APP } from "@/lib/constants/app";
import { env } from "@/lib/env";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

// Coordinates, execution traces, model ids and data tables all render in this face — the technical
// register the design report calls for.
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(env.NEXT_PUBLIC_APP_URL),
  title: {
    default: `${APP.name} · Mission Command Center`,
    template: `%s · ${APP.name}`,
  },
  description: APP.shortDescription,
  applicationName: APP.name,
  keywords: [
    "satellite imagery analysis",
    "earth observation",
    "remote sensing AI",
    "change detection",
    "SAR analysis",
    "geospatial intelligence",
    "agentic AI",
  ],
  authors: [{ name: APP.name }],
  openGraph: {
    type: "website",
    siteName: APP.name,
    title: `${APP.name} — ${APP.fullName}`,
    description: APP.shortDescription,
    url: env.NEXT_PUBLIC_APP_URL,
  },
  twitter: {
    card: "summary_large_image",
    title: `${APP.name} — ${APP.fullName}`,
    description: APP.shortDescription,
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: "#0A0D14",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${jetbrainsMono.variable} dark`} suppressHydrationWarning>
      <body className="bg-background text-foreground antialiased" suppressHydrationWarning>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
