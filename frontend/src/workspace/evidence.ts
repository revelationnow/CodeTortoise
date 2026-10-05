/** Evidence lines name workspace files; the detail panel opens depot paths. The depot path of a workspace file is the
 * candidate sharing the longest tail of path segments with it (at least the file name), if exactly one does. */
export function depotFor(file: string, depots: Iterable<string>): string | null {
  if (file.startsWith("//")) return file;
  const mine = file.split("/").reverse();
  let best: string | null = null, bestN = 0, tie = false;
  for (const d of new Set(depots)) {
    const theirs = d.split("/").reverse();
    let n = 0;
    while (n < mine.length && n < theirs.length && mine[n] === theirs[n] && mine[n]) n++;
    if (n > bestN) { best = d; bestN = n; tie = false; } else if (n === bestN && n > 0) tie = true;
  }
  return bestN > 0 && !tie ? best : null;
}
