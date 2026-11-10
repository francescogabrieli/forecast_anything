const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const replayButton = document.querySelector<HTMLButtonElement>('.replay-button');
const chapters = document.querySelectorAll<HTMLElement>('.chapter-section');

let observer: IntersectionObserver | undefined;
let replay: Animation[] = [];

function cancelReplay() {
  replay.forEach(animation => animation.cancel());
  replay = [];
}

function syncMotionPreference() {
  observer?.disconnect();
  cancelReplay();

  if (replayButton) replayButton.hidden = reducedMotion.matches;
  if (reducedMotion.matches || !('IntersectionObserver' in window)) return;

  observer = new IntersectionObserver(entries => {
    for (const { target, isIntersecting } of entries) {
      if (!isIntersecting) continue;
      target.classList.add('chapter-entered');
      observer?.unobserve(target);
    }
  }, { threshold: 0.15 });

  chapters.forEach(chapter => {
    if (!chapter.classList.contains('chapter-entered')) observer?.observe(chapter);
  });
}

replayButton?.addEventListener('click', () => {
  if (reducedMotion.matches) return;
  cancelReplay();

  const charts = document.querySelectorAll<SVGSVGElement>('#demo svg[data-forecast-chart]');
  for (const chart of charts) {
    const cutoff = chart.querySelector('.cutoff-rule');
    if (cutoff) {
      replay.push(cutoff.animate([
        { strokeWidth: '1.7' }, { strokeWidth: '4' }, { strokeWidth: '1.7' },
      ], { duration: 400, easing: 'ease-in-out' }));
    }

    chart.querySelectorAll('[data-series="timestral"], [data-series="seasonal"]').forEach(point => {
      replay.push(point.animate([
        { scale: '1' }, { scale: '1.5' }, { scale: '1' },
      ], { delay: 320, duration: 420, easing: 'ease-in-out' }));
    });
  }

  document.querySelectorAll('.value-list dd').forEach(value => {
    replay.push(value.animate([
      { transform: 'translateY(0)' }, { transform: 'translateY(-3px)' }, { transform: 'translateY(0)' },
    ], { delay: 560, duration: 300, easing: 'ease-in-out' }));
  });
});

reducedMotion.addEventListener('change', syncMotionPreference);
syncMotionPreference();
