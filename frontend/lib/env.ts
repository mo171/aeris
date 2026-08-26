/**
 * @file lib/env.ts
 * @description Centralized environment variable validation and type-safe access
 */

export const env = {
  // App Config
  NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL,
  
  // API Config
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,

};
