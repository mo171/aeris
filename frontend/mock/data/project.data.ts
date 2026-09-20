// mock/data/project.data.ts — generates mock projects.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.

import type { z } from "zod";

import type { projectSchema } from "@/features/project/schemas/project.schema";

import { createSeededRandom, pickOne, randomInteger } from "../transport/deterministic-random";
import { MOCK_AREAS } from "./geography";

type Project = z.infer<typeof projectSchema>;

const PROJECT_SEED = 12345;
const REFERENCE_TIME_MS = Date.parse("2026-08-26T09:00:00.000Z");

let cachedProjects: Project[] | null = null;

export function getMockProjects(): Project[] {
  if (!cachedProjects) {
    cachedProjects = generateProjects();
  }
  return cachedProjects;
}

function generateProjects(): Project[] {
  const random = createSeededRandom(PROJECT_SEED);
  const projects: Project[] = [];
  
  const names = [
    "Mumbai Coastal Monitoring",
    "Delhi NCR Urban Expansion",
    "Kerala Flood Assessment",
    "Sundarbans Mangrove Mapping",
    "Chennai Port Activity",
    "Punjab Crop Yield Watch"
  ];
  
  for (let index = 0; index < names.length; index += 1) {
    const area = pickOne(random, MOCK_AREAS);
    const createdAtMs = REFERENCE_TIME_MS - randomInteger(random, 10, 100) * 86400000;
    
    projects.push({
      id: `p-${index + 1}`,
      name: names[index],
      areaOfInterestName: area.name,
      areaOfInterest: {
        west: area.longitude - 0.1,
        south: area.latitude - 0.1,
        east: area.longitude + 0.1,
        north: area.latitude + 0.1,
      },
      centroid: { latitude: area.latitude, longitude: area.longitude },
      createdAt: new Date(createdAtMs).toISOString(),
      updatedAt: new Date(createdAtMs + 3600000).toISOString(),
      lastActivityAt: new Date(createdAtMs + 86400000).toISOString(),
    });
  }
  
  return projects;
}

export function selectMockProjectPage(cursor: string | null, limit: number) {
  const projects = getMockProjects();
  const parsedCursor = cursor ? Number.parseInt(cursor, 10) : 0;
  const startIndex = Number.isFinite(parsedCursor) && parsedCursor > 0 ? parsedCursor : 0;
  const endIndex = Math.min(startIndex + limit, projects.length);

  return {
    items: projects.slice(startIndex, endIndex),
    nextCursor: endIndex < projects.length ? String(endIndex) : null,
    totalCount: projects.length,
  };
}

export function getMockProject(id: string): Project | null {
  const projects = getMockProjects();
  return projects.find((p) => p.id === id) ?? null;
}

export function createMockProject(request: { name: string; areaOfInterestName: string; areaOfInterest: any }): Project {
  const projects = getMockProjects();
  const now = new Date().toISOString();
  
  const newProject: Project = {
    id: `p-${projects.length + 1}`,
    name: request.name,
    areaOfInterestName: request.areaOfInterestName,
    areaOfInterest: request.areaOfInterest,
    centroid: {
      latitude: (request.areaOfInterest.north + request.areaOfInterest.south) / 2,
      longitude: (request.areaOfInterest.east + request.areaOfInterest.west) / 2,
    },
    createdAt: now,
    updatedAt: now,
    lastActivityAt: now,
  };
  
  projects.unshift(newProject);
  return newProject;
}
