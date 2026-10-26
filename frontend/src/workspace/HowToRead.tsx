/** How to read a review (spec 2026-10-16-outline-and-causes §1.1), for a reader new to CodeTortoise: a panel the
 * header's ⋯ menu opens at `top` (spec 2026-10-25-review-ui-redesign §2.2); the menu closes it. */
export default function HowToRead({ top }: { top: number }) {
  return (
    <div className="ws-help-pop rm-panel" role="dialog" aria-label="How to read this page" tabIndex={-1} style={{ top }}>
      <h2>How to read this page</h2>
      <ul>
        <li><b>The outline</b> on the left lists the change's threads — stories joined by calls or shared data, lettered
          A, B… — and each thread's stories in reading order; the story you are on shows its flows.</li>
        <li><b>Checks</b> at the top of the outline lists what needs a reviewer's eye, grouped by the change that raised
          it. <b>Showing</b> hides kinds of check; Confirm is hidden until you show it.</li>
        <li><b>A check</b> opens beside the page: the change that raised it above each place it asks you to look at.
          <b> Looks fine &amp; next</b> clears a place for everyone, <b>All look fine</b> clears them all, <b>Comment</b>
          starts a thread. Keys: J next, K back, F looks fine &amp; next.</li>
        <li><b>Next open check ›</b> goes to the next place still open, in reading order.</li>
        <li><b>A story</b> has tabs: Flows (each path through the change, with its checks), Before → after, Where, Call
          paths, Code, Graph and Talk.</li>
        <li><b>Mark as read</b> ticks a story for you alone; the top bar counts the stories you have read and the checks
          still open.</li>
        <li><b>The side panel</b> keeps a tab per thing you open; <b>Focus</b> folds the outline to give it room.</li>
        <li>A faint violet line at the left of a paragraph marks text the AI wrote.</li>
      </ul>
    </div>
  );
}
