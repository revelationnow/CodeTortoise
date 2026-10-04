/** Call `fn` every `ms` after the previous call has settled (never two at once; a failure doesn't stop it). */
export function pollLoop(fn: () => Promise<unknown>, ms: number): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const next = () => {
    timer = setTimeout(() => {
      fn().catch(() => { /* shown by the next successful poll */ }).finally(() => { if (!stopped) next(); });
    }, ms);
  };
  next();
  return () => { stopped = true; clearTimeout(timer); };
}
