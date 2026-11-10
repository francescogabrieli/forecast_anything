const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const replayButton = document.querySelector<HTMLButtonElement>('.replay-button');
const heroChart = document.querySelector<SVGSVGElement>('.chart-preview');
const demoCharts = document.querySelectorAll<SVGSVGElement>('#demo svg[data-forecast-chart]');
const chapters = document.querySelectorAll<HTMLElement>('.chapter-section');

let observer: IntersectionObserver | undefined;
let heroPlayed = false;
let heroAnimations: Animation[] = [];
let replayAnimations: Animation[] = [];

function revealChart(chart: SVGSVGElement, start = 0) {
  const historyDuration = 620;
  return Array.from(chart.querySelectorAll<SVGRectElement>('rect[data-reveal]'), mask => {
    const isHistory = mask.dataset.reveal === 'history';
    return mask.animate([
      { width: '0px' },
      { width: `${mask.width.baseVal.value}px` },
    ], {
      delay: start + (isHistory ? 0 : historyDuration),
      duration: isHistory ? historyDuration : 320,
      easing: isHistory ? 'linear' : 'cubic-bezier(.22, 1, .36, 1)',
      fill: 'backwards',
    });
  });
}

function syncMotionPreference() {
  observer?.disconnect();
  [...heroAnimations, ...replayAnimations].forEach(animation => animation.cancel());
  heroAnimations = [];
  replayAnimations = [];

  if (replayButton) replayButton.hidden = reducedMotion.matches;
  if (reducedMotion.matches || !('IntersectionObserver' in window)) return;

  observer = new IntersectionObserver(entries => {
    for (const { target, isIntersecting } of entries) {
      if (!isIntersecting) continue;
      if (target === heroChart) {
        heroPlayed = true;
        heroAnimations = revealChart(heroChart, 350);
      } else {
        target.classList.add('chapter-entered');
      }
      observer?.unobserve(target);
    }
  }, { threshold: 0.15 });

  if (heroChart && !heroPlayed) observer.observe(heroChart);
  chapters.forEach(chapter => {
    if (!chapter.classList.contains('chapter-entered')) observer?.observe(chapter);
  });
}

replayButton?.addEventListener('click', () => {
  if (reducedMotion.matches) return;
  replayAnimations.forEach(animation => animation.cancel());
  replayAnimations = Array.from(demoCharts).flatMap(chart => revealChart(chart));
});

reducedMotion.addEventListener('change', syncMotionPreference);
syncMotionPreference();
