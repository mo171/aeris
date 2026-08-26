// mock/transport/deterministic-random.ts — seeded pseudo-random generator for stable mock data.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : A small, fast, seeded PRNG plus helpers for picking numbers and array elements.
// where : Used by every generator in mock/data.
// how   : Mock data must be identical on every reload. Math.random() would reshuffle the catalogue on each
//         refresh, which makes visual review and performance comparison impossible — you could never tell
//         whether a layout changed because of your code or because the data moved. mulberry32 gives a
//         deterministic sequence from a fixed seed at negligible cost.

export function createSeededRandom(seed: number): () => number {
  let state = seed >>> 0;

  return function next(): number {
    state += 0x6d2b79f5;
    let result = state;
    result = Math.imul(result ^ (result >>> 15), result | 1);
    result ^= result + Math.imul(result ^ (result >>> 7), result | 61);
    return ((result ^ (result >>> 14)) >>> 0) / 4294967296;
  };
}

export function randomInteger(random: () => number, minimum: number, maximum: number): number {
  return Math.floor(random() * (maximum - minimum + 1)) + minimum;
}

export function randomFloat(random: () => number, minimum: number, maximum: number): number {
  return random() * (maximum - minimum) + minimum;
}

export function pickOne<TItem>(random: () => number, items: readonly TItem[]): TItem {
  return items[Math.floor(random() * items.length)];
}

/** Weighted pick. Weights need not sum to one. */
export function pickWeighted<TItem>(
  random: () => number,
  entries: readonly { value: TItem; weight: number }[],
): TItem {
  const totalWeight = entries.reduce((sum, entry) => sum + entry.weight, 0);
  let threshold = random() * totalWeight;

  for (const entry of entries) {
    threshold -= entry.weight;
    if (threshold <= 0) {
      return entry.value;
    }
  }

  return entries[entries.length - 1].value;
}
